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
    """从公开网页抓取最新开奖数据(纯Python, 无Puppeteer依赖)"""
    existing = fetcher.get_all_draws()
    last_date = existing[-1]["draw_date"] if existing else "2020-01-01"
    
    new_records = []
    
    # 数据源1: california.lottonumbers.com (HTML解析)
    try:
        url = "https://california.lottonumbers.com/fantasy-5/past-numbers/2026"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ca-lottery-predictor)',
            'Accept': 'text/html',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        
        # 解析HTML中的开奖数据 (匹配类似: <td>07/01/2026</td> ... <td>5</td><td>11</td>... )
        # 通用匹配: 日期格式 MM/DD/YYYY 或 YYYY-MM-DD, 后跟5个1-39的数字
        date_pattern = r'(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})'
        num_pattern = r'(?<![a-zA-Z])(\d{1,2})(?![a-zA-Z])'
        
        # 更健壮的提取方式: 找所有包含日期和5个数字的行
        rows = re.findall(
            r'(?:20\d{2}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]20\d{2})[^<]*?(?:<td[^>]*>|\s+)(\d{1,2})[^<]*?(?:<td[^>]*>|\s+)(\d{1,2})[^<]*?(?:<td[^>]*>|\s+)(\d{1,2})[^<]*?(?:<td[^>]*>|\s+)(\d{1,2})[^<]*?(?:<td[^>]*>|\s+)(\d{1,2})',
            html
        )
        
        # 备用: 从页面中提取所有日期-数字组合
        # 先找所有日期, 然后在每个日期后面找5个1-39的数字
        all_dates = re.findall(r'(20\d{2}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]20\d{2})', html)
        all_nums_in_range = [int(n) for n in re.findall(r'(?<![a-zA-Z">])(\d{1,2})(?![a-zA-Z"<])', html) if 1 <= int(n) <= 39]
        
        # 尝试提取最近5天的数据
        for date_str in all_dates[:30]:  # 只看最近的日期
            # 统一日期格式为 YYYY-MM-DD
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts[0]) == 4:  # YYYY/MM/DD
                    normalized = f"{parts[0]}-{parts[1]}-{parts[2]}"
                else:  # MM/DD/YYYY
                    normalized = f"{parts[2]}-{parts[0]}-{parts[1]}"
            else:
                normalized = date_str
            
            if normalized <= last_date:
                continue  # 跳过已存在的日期
            
            # 在这个日期附近找5个数字(在HTML中日期和数字通常在同一行或相邻行)
            # 使用简单策略: 在html中找该日期出现的位置, 然后取后面最近的5个1-39数字
            pos = html.find(date_str)
            if pos >= 0:
                # 从日期位置往后200字符内找数字
                chunk = html[pos:pos+200]
                nums_in_chunk = [int(n) for n in re.findall(r'(?<![a-zA-Z">])(\d{1,2})(?![a-zA-Z"<])', chunk) if 1 <= int(n) <= 39]
                if len(nums_in_chunk) >= 5:
                    # 取前5个有效数字
                    numbers = nums_in_chunk[:5]
                    new_records.append({
                        'draw_date': normalized,
                        'num1': numbers[0], 'num2': numbers[1],
                        'num3': numbers[2], 'num4': numbers[3],
                        'num5': numbers[4],
                        'jackpot_amount': 0,
                    })
    except Exception as e:
        print(f"  ⚠️ california.lottonumbers.com抓取失败: {e}")

    # 数据源2: lotteryusa.com (更可靠, 格式更简单)
    try:
        url2 = "https://www.lotteryusa.com/california/fantasy-5/"
        req2 = urllib.request.Request(url2, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ca-lottery-predictor)',
            'Accept': 'text/html',
        })
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            html2 = resp2.read().decode('utf-8', errors='replace')
        
        # lotteryusa.com格式: 日期后面紧跟5个数字
        # 匹配: "Monday, Jun 29, 2026" 后面有 5个 1-39的数字
        date_blocks = re.finditer(
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*'
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}',
            html2
        )
        
        for match in date_blocks:
            raw_date = match.group()
            # 转换为 YYYY-MM-DD
            dt = datetime.strptime(raw_date, "%A, %b %d, %Y")
            normalized = dt.strftime("%Y-%m-%d")
            
            if normalized <= last_date:
                continue
            
            # 在日期块后面找5个数字
            chunk = html2[match.start():match.start()+300]
            nums = [int(n) for n in re.findall(r'(?<![a-zA-Z">])(\d{1,2})(?![a-zA-Z"<])', chunk) if 1 <= int(n) <= 39]
            if len(nums) >= 5:
                numbers = nums[:5]
                # 检查是否已存在(从数据源1可能已获取)
                if not any(r['draw_date'] == normalized for r in new_records):
                    new_records.append({
                        'draw_date': normalized,
                        'num1': numbers[0], 'num2': numbers[1],
                        'num3': numbers[2], 'num4': numbers[3],
                        'num5': numbers[4],
                        'jackpot_amount': 0,
                    })
    except Exception as e:
        print(f"  ⚠️ lotteryusa.com抓取失败: {e}")

    # 数据源3: gidapp.com (JSON API, 最简洁)
    try:
        url3 = "https://us.gidapp.com/lottery/ca/fantasy-5"
        req3 = urllib.request.Request(url3, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ca-lottery-predictor)',
        })
        with urllib.request.urlopen(req3, timeout=30) as resp3:
            html3 = resp3.read().decode('utf-8', errors='replace')
        
        # gidapp格式: "Winning Numbers for Wednesday, July 1, 2026" 或类似
        date_blocks = re.finditer(
            r'Winning Numbers for\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}',
            html3
        )
        for match in date_blocks:
            raw_date = match.group().replace('Winning Numbers for ', '')
            dt = datetime.strptime(raw_date, "%A, %B %d, %Y")
            normalized = dt.strftime("%Y-%m-%d")
            
            if normalized <= last_date:
                continue
            
            chunk = html3[match.start():match.start()+400]
            nums = [int(n) for n in re.findall(r'(?<![a-zA-Z">])(\d{1,2})(?![a-zA-Z"<])', chunk) if 1 <= int(n) <= 39]
            if len(nums) >= 5:
                if not any(r['draw_date'] == normalized for r in new_records):
                    new_records.append({
                        'draw_date': normalized,
                        'num1': nums[0], 'num2': nums[1],
                        'num3': nums[2], 'num4': nums[3],
                        'num5': nums[4],
                        'jackpot_amount': 0,
                    })
    except Exception as e:
        print(f"  ⚠️ gidapp.com抓取失败: {e}")

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
