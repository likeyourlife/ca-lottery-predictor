#!/usr/bin/env python3
"""
每日自动化脚本 - 采集前日开奖数据→回测→优化→形成新的预测
在每天9:40 AM (Mon-Sat) 由WorkBuddy Automation触发
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GAME, ENGINE_WEIGHTS, TOP_N_LEVELS
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from engines.engine_fusion import EngineFusion
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
from output.topn_selector import TopNSelector
from output.report_formatter import ReportFormatter
from backtest.backtest_runner import BacktestRunner


def daily_pipeline(game_key: str = DEFAULT_GAME):
    """每日自动化流水线"""
    
    print("=" * 60)
    print("CALIFORNIA FANTASY 5 - 每日预测流水线")
    print("=" * 60)
    
    # Step 1: 初始化/更新数据
    print("\n[Step 1] 数据初始化...")
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    print(f"  当前数据量: {len(records)} 期")
    
    # Step 2: 运行回测(100期)
    print("\n[Step 2] 100期回测验证...")
    runner = BacktestRunner(game_key)
    bt_result = runner.run_backtest(window=100)
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
