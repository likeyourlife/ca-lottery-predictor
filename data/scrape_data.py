#!/usr/bin/env python3
"""
数据补充脚本 - 从lottery.net抓取2022-2024年完整数据
lottery.net的HTML是静态的，可以用urllib+解析获取
"""

import sys
import json
import re
import urllib.request
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def fetch_lottery_net_data(year: int) -> list:
    """从lottery.net抓取指定年份的Fantasy 5数据"""
    url = f"https://www.lottery.net/california/fantasy-5/numbers/{year}"
    print(f"  正在抓取 {year} 年数据: {url}")
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    })
    
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  抓取失败: {e}")
        return []
    
    # 解析HTML中的日期和号码
    # lottery.net格式: 月份表格，每行是日期 + 5个号码
    draws = []
    
    # 尝试从HTML中提取所有日期+号码的组合
    # 格式: <td>January 1, 2024</td>...<td>1</td><td>3</td><td>15</td><td>28</td><td>33</td>
    
    # 方法1: 搜索所有日期文本
    month_map = {
        'January': '01', 'February': '02', 'March': '03', 'April': '04',
        'May': '05', 'June': '06', 'July': '07', 'August': '08',
        'September': '09', 'October': '10', 'November': '11', 'December': '12',
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'Jun': '06', 'Jul': '07', 'Aug': '08', 'Sep': '09',
        'Oct': '10', 'Nov': '11', 'Dec': '12',
    }
    
    # 从HTML中提取表格数据
    # 搜索包含年份的表格行
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    
    for row in rows:
        # 提取日期
        date_match = re.search(
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
            row
        )
        
        if date_match:
            day = int(date_match.group(1))
            yr = int(date_match.group(2))
            month_str = date_match.group(0).split()[0]
            month = month_map.get(month_str, '01')
            date_str = f"{yr}-{month}-{day:02d}"
            
            # 提取号码 (1-39范围)
            nums = re.findall(r'<td[^>]*>\s*(\d{1,2})\s*</td>', row)
            valid_nums = [int(n) for n in nums if 1 <= int(n) <= 39]
            
            if len(valid_nums) == 5:
                draws.append({
                    "draw_date": date_str,
                    "num1": str(valid_nums[0]),
                    "num2": str(valid_nums[1]),
                    "num3": str(valid_nums[2]),
                    "num4": str(valid_nums[3]),
                    "num5": str(valid_nums[4]),
                    "jackpot_amount": "0",
                })
    
    print(f"  从 {year} 年HTML中解析到 {len(draws)} 条数据")
    return draws


def main():
    """主函数: 抓取2022-2024年数据并合并"""
    
    print("=" * 60)
    print("数据补充: 抓取2022-2024年完整Fantasy 5历史数据")
    print("=" * 60)
    
    all_new_draws = []
    
    for year in [2022, 2023, 2024]:
        draws = fetch_lottery_net_data(year)
        all_new_draws.extend(draws)
    
    # 也抓取2025年1-7月
    draws_2025 = fetch_lottery_net_data(2025)
    all_new_draws.extend(draws_2025)
    
    # 去重 + 按日期排序
    existing_dates = set()
    
    # 加载已有数据
    from data.fetcher import init_fantasy5_data
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    
    for r in records:
        existing_dates.add(r.get("draw_date", r.get("date", "")))
    
    # 过滤新数据(去重)
    new_draws = [d for d in all_new_draws if d["draw_date"] not in existing_dates]
    new_draws.sort(key=lambda d: d["draw_date"])
    
    print(f"\n已有数据: {len(records)} 条, 日期范围: {min(existing_dates)} - {max(existing_dates)}")
    print(f"新数据(去重后): {len(new_draws)} 条")
    
    if new_draws:
        # 合并到历史数据
        csv_path = PROJECT_ROOT / "data" / "fantasy5" / "history.csv"
        
        # 写入CSV格式追加
        with open(csv_path, "a", encoding="utf-8") as f:
            for d in new_draws:
                line = f"{d['draw_date']},{d['num1']},{d['num2']},{d['num3']},{d['num4']},{d['num5']},{d['jackpot_amount']}\n"
                f.write(line)
        
        print(f"  ✅ 新增 {len(new_draws)} 条数据到 {csv_path}")
        print(f"  合并后总数据量: {len(records) + len(new_draws)} 条")
        
        # 保存新增数据详情
        supplement_path = PROJECT_ROOT / "data" / "fantasy5" / "supplement_log.json"
        with open(supplement_path, "w", encoding="utf-8") as f:
            json.dump({
                "supplement_date": datetime.now().isoformat(),
                "new_draws_count": len(new_draws),
                "total_draws": len(records) + len(new_draws),
                "new_date_range": f"{new_draws[0]['draw_date']} - {new_draws[-1]['draw_date']}" if new_draws else "",
            }, f, ensure_ascii=False, indent=2)
    else:
        print("  ℹ️ 无新增数据(所有日期已存在)")
    
    print("\n" + "=" * 60)
    print("数据补充完成 ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
