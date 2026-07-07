#!/usr/bin/env python3
"""
每日自动化脚本 - 采集最新开奖数据→回测→预测→输出
在每天9:40 AM (Mon-Sat) 由GitHub Actions cron或手动触发
"""

import sys
import json
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GAME, ENGINE_WEIGHTS, TOP_N_LEVELS, BACKTEST_CONFIG
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from engines.engine_fusion import EngineFusion
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
from output.topn_selector import TopNSelector
from output.report_formatter import ReportFormatter
from backtest.backtest_runner import BacktestRunner


def fetch_new_draws_from_web(fetcher: DataFetcher) -> int:
    """从公开网页抓取最新开奖数据(纯Python, 无Puppeteer依赖)
    
    数据源优先级(2026-07更新):
    1. california.lottonumbers.com — 187期可提取, <li class="ball">格式
    2. lotterycorner.com — 187期可提取, <div class="number">格式  
    3. lotteryusa.com/year — SSR渲染, 需特定正则
    
    已失效源(2026-07): calottery.com(403), gidapp.com(403)
    """
    existing = fetcher.get_all_draws()
    last_date = existing[-1]["draw_date"] if existing else "2020-01-01"
    
    new_records = []
    current_year = datetime.now().year
    UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    # ── 数据源1: california.lottonumbers.com ──
    # 格式: <td>MM/DD/YYYY</td> ... <li class="ball ...">NUM</li>
    try:
        url = f"https://california.lottonumbers.com/fantasy-5/past-numbers/{current_year}"
        req = urllib.request.Request(url, headers={
            'User-Agent': UA, 'Accept': 'text/html',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        
        for date_match in re.finditer(r'(\d{2}/\d{2}/\d{4})', html):
            raw = date_match.group(1)
            parts = raw.split('/')
            normalized = f'{parts[2]}-{parts[0]}-{parts[1]}'
            
            if normalized <= last_date:
                continue
            
            chunk = html[date_match.start():date_match.start() + 500]
            # 匹配 <li class="ball ...">NUM</li>
            nums = [int(n) for n in re.findall(
                r'<li[^>]*class="ball[^"]*"[^>]*>\s*(\d{1,2})\s*</li>', chunk
            ) if 1 <= int(n) <= 39]
            
            if len(nums) >= 5 and not any(r['draw_date'] == normalized for r in new_records):
                new_records.append({
                    'draw_date': normalized,
                    'num1': nums[0], 'num2': nums[1],
                    'num3': nums[2], 'num4': nums[3],
                    'num5': nums[4],
                    'jackpot_amount': 0,
                })
        
        print(f"  📡 california.lottonumbers.com: 提取 {len([r for r in new_records if r['draw_date'] > last_date])} 条新数据")
    except Exception as e:
        print(f"  ⚠️ california.lottonumbers.com失败: {e}")

    # ── 数据源2: lotterycorner.com ──
    # 格式: Month DD, YYYY ... <div class="number">NUM</div>
    try:
        url2 = f"https://lotterycorner.com/ca/fantasy-5/{current_year}"
        req2 = urllib.request.Request(url2, headers={
            'User-Agent': UA, 'Accept': 'text/html',
        })
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            html2 = resp2.read().decode('utf-8', errors='replace')
        
        months = 'January|February|March|April|May|June|July|August|September|October|November|December'
        for date_match in re.finditer(f'({months})\\s+(\\d{{1,2}}),\\s+(\\d{{4}})', html2):
            raw = date_match.group()
            dt = datetime.strptime(raw, '%B %d, %Y')
            normalized = dt.strftime('%Y-%m-%d')
            
            if normalized <= last_date:
                continue
            
            chunk = html2[date_match.start():date_match.start() + 500]
            # 匹配 <div class="number">NUM</div>
            nums = [int(n) for n in re.findall(
                r'class="number"[^>]*>\s*(\d{1,2})\s*</div>', chunk
            ) if 1 <= int(n) <= 39]
            
            if len(nums) >= 5 and not any(r['draw_date'] == normalized for r in new_records):
                new_records.append({
                    'draw_date': normalized,
                    'num1': nums[0], 'num2': nums[1],
                    'num3': nums[2], 'num4': nums[3],
                    'num5': nums[4],
                    'jackpot_amount': 0,
                })
        
        print(f"  📡 lotterycorner.com: 补充提取完成")
    except Exception as e:
        print(f"  ⚠️ lotterycorner.com失败: {e}")

    # ── 数据源3: lotteryusa.com/year ──
    # SSR渲染HTML, 日期在文本中, 号码在<span>NUM</span>标签
    try:
        url3 = f"https://www.lotteryusa.com/california/fantasy-5/year"
        req3 = urllib.request.Request(url3, headers={
            'User-Agent': UA, 'Accept': 'text/html',
        })
        with urllib.request.urlopen(req3, timeout=30) as resp3:
            html3 = resp3.read().decode('utf-8', errors='replace')
        
        # lotteryusa格式: "Day, Mon DD, YYYY" + numbers in nearby tags
        days = 'Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday'
        mons = 'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec'
        for date_match in re.finditer(
            f'({days}),\\s*({mons})\\s+(\\d{{1,2}}),\\s+(\\d{{4}})', html3
        ):
            raw = date_match.group()
            dt = datetime.strptime(raw, '%A, %b %d, %Y')
            normalized = dt.strftime('%Y-%m-%d')
            
            if normalized <= last_date:
                continue
            
            chunk = html3[date_match.start():date_match.start() + 400]
            # 号码可能在 <span>NUM</span> 或纯文本中
            nums = [int(n) for n in re.findall(
                r'<span[^>]*>\s*(\d{1,2})\s*</span>', chunk
            ) if 1 <= int(n) <= 39]
            if len(nums) < 5:
                nums = [int(n) for n in re.findall(
                    r'>(\d{1,2})<', chunk
                ) if 1 <= int(n) <= 39]
            
            if len(nums) >= 5 and not any(r['draw_date'] == normalized for r in new_records):
                new_records.append({
                    'draw_date': normalized,
                    'num1': nums[0], 'num2': nums[1],
                    'num3': nums[2], 'num4': nums[3],
                    'num5': nums[4],
                    'jackpot_amount': 0,
                })
        
        print(f"  📡 lotteryusa.com/year: 补充提取完成")
    except Exception as e:
        print(f"  ⚠️ lotteryusa.com/year失败: {e}")

    # 添加新数据到CSV
    if new_records:
        # 按日期排序并去重
        new_records.sort(key=lambda r: r['draw_date'])
        seen = set(existing_record['draw_date'] for existing_record in existing)
        unique_new = [r for r in new_records if r['draw_date'] not in seen]
        
        if unique_new:
            fetcher.append_records(unique_new)
            print(f"  ✅ 新增 {len(unique_new)} 条数据: {unique_new[0]['draw_date']} ~ {unique_new[-1]['draw_date']}")
            for r in unique_new:
                print(f"    {r['draw_date']}: {r['num1']},{r['num2']},{r['num3']},{r['num4']},{r['num5']}")
        else:
            print(f"  ℹ️ 抓取到 {len(new_records)} 条但全部已存在")
    else:
        print(f"  ℹ️ 未能抓取新数据(最新数据仍为 {last_date})")
    
    return len(unique_new) if new_records else 0


def daily_pipeline(game_key: str = DEFAULT_GAME):
    """每日自动化流水线"""
    
    print("=" * 60)
    print("CALIFORNIA FANTASY 5 - 每日预测流水线")
    print("=" * 60)
    
    # Step 1: 抓取最新数据 + 初始化
    bt_window = BACKTEST_CONFIG.get("window", 200)
    print("\n[Step 1] 数据更新与初始化...")
    fetcher = init_fantasy5_data()
    new_count = fetch_new_draws_from_web(fetcher)
    # 重新获取(可能已有新数据)
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    print(f"  当前数据量: {len(records)} 期 | 回测窗口: {bt_window}")
    runner = BacktestRunner(game_key)
    bt_result = runner.run_backtest(window=bt_window)
    avoid_stats = bt_result["avoid_stats"]
    for level in TOP_N_LEVELS:
        stats = avoid_stats[level]
        beat = "✅" if stats["beat_baseline"] else "❌"
        print(f"  {beat} Top{level}: {stats['hit_rate']:.2%} | 基线={stats['random_baseline']:.2%} | margin={stats['margin']:+.2f}%")
    
    # Step 3: 生成预测
    print("\n[Step 3] 生成当日预测...")
    formatter = ReportFormatter(game_key)
    report = formatter.format_full_report(records)
    print(report)
    
    # Step 4: 输出JSON格式结果(供前端使用)
    print("\n[Step 4] 输出JSON结果...")
    json_report = formatter.format_json_report(records)
    output_path = PROJECT_ROOT / "data" / "fantasy5" / "daily_prediction.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    print(f"  JSON已保存: {output_path}")
    
    # Step 5: 保存回测结果
    bt_output = {
        "date": records[-1]["draw_date"] if records else "unknown",
        "data_count": len(records),
        "avoid_stats": {
            str(level): {
                "hit_rate": avoid_stats[level]["hit_rate"],
                "random_baseline": avoid_stats[level]["random_baseline"],
                "margin": avoid_stats[level]["margin"],
                "beat_baseline": avoid_stats[level]["beat_baseline"],
            }
            for level in TOP_N_LEVELS
        },
        "weights": ENGINE_WEIGHTS.get(game_key, {}),
    }
    bt_path = PROJECT_ROOT / "data" / "fantasy5" / "backtest_result.json"
    with open(bt_path, "w", encoding="utf-8") as f:
        json.dump(bt_output, f, ensure_ascii=False, indent=2)
    print(f"  回测结果已保存: {bt_path}")
    
    print("\n" + "=" * 60)
    print("每日流水线完成 ✅")
    print("=" * 60)


if __name__ == "__main__":
    daily_pipeline()
