#!/usr/bin/env python3
"""
合并 Puppeteer 抓取数据到现有 Fantasy 5 数据集
用法: python data/merge_scraped_data.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_scraped_json(path: str) -> list:
    """加载 Puppeteer 抓取的 JSON 数据"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"  加载抓取数据: {len(data)} 条 from {path}")
    return data


def merge_to_existing(scraped_draws: list) -> dict:
    """合并抓取数据到现有数据集"""
    
    from data.fetcher import init_fantasy5_data
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    
    # 已有日期集合
    existing_dates = set()
    for r in records:
        existing_dates.add(r.get("draw_date", r.get("date", "")))
    
    # 过滤新数据(去重)
    new_draws = [d for d in scraped_draws if d["draw_date"] not in existing_dates]
    new_draws.sort(key=lambda d: d["draw_date"])
    
    print(f"  已有数据: {len(records)} 条, 日期: {min(existing_dates)} - {max(existing_dates)}")
    print(f"  抓取数据: {len(scraped_draws)} 条")
    print(f"  新增数据(去重后): {len(new_draws)} 条")
    
    if new_draws:
        # 将新数据追加到 supplement 数据文件
        supplement_path = PROJECT_ROOT / "data" / "supplement_scraped.py"
        
        # 生成 Python 数据文件格式
        draws_code = json.dumps(new_draws, ensure_ascii=False, indent=4)
        code = f'''#!/usr/bin/env python3
"""Puppeteer抓取补充数据 - 自动生成于 {datetime.now().isoformat()}"""
# 新增 {len(new_draws)} 条数据, 日期范围: {new_draws[0]["draw_date"]} - {new_draws[-1]["draw_date"]}

SUPPLEMENT_SCRAPED_DATA = {draws_code}
'''
        
        with open(supplement_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"  ✅ 生成补充数据文件: {supplement_path}")
        print(f"  合并后总量: {len(records) + len(new_draws)} 条")
        
        # 更新 fetcher.py 以加载此数据文件
        print(f"\n  ⚠️  需要手动更新 data/fetcher.py 添加 SUPPLEMENT_SCRAPED_DATA 的加载逻辑")
        print(f"  或重新运行 daily_pipeline.py 自动整合")
    else:
        print("  ℹ️ 无新增数据(所有日期已存在)")
    
    return {
        "existing": len(records),
        "scraped_total": len(scraped_draws),
        "new_unique": len(new_draws),
        "merged_total": len(records) + len(new_draws),
    }


def main():
    """主函数"""
    
    scraped_dir = PROJECT_ROOT / "data" / "scraped_data"
    all_file = scraped_dir / "fantasy5_all_scraped.json"
    
    if not all_file.exists():
        print("❌ 未找到抓取数据文件: " + str(all_file))
        print("请先运行: node data/puppeteer_scrape.js")
        return
    
    print("=" * 60)
    print("合并 Puppeteer 抓取数据到现有数据集")
    print("=" * 60)
    
    scraped_draws = load_scraped_json(str(all_file))
    result = merge_to_existing(scraped_draws)
    
    print("\n" + "=" * 60)
    print(f"合并完成 ✅")
    print(f"  已有: {result['existing']} | 新增: {result['new_unique']} | 总计: {result['merged_total']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
