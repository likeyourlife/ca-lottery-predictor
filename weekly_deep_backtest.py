#!/usr/bin/env python3
"""
每周深度回测脚本 - 深度回测验证预测准确率，并让预测引擎自动学习优化
在每周周一由WorkBuddy Automation触发
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GAME, ENGINE_WEIGHTS, TOP_N_LEVELS, BACKTEST_CONFIG
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from backtest.backtest_runner import BacktestRunner
from backtest.weight_optimizer import WeightOptimizer
from output.report_formatter import ReportFormatter


def weekly_deep_backtest(game_key: str = DEFAULT_GAME):
    """每周深度回测 + 自动学习优化"""
    
    print("=" * 60)
    print("CALIFORNIA FANTASY 5 - 每周深度回测 + 自动学习优化")
    print("=" * 60)
    
    # Step 1: 初始化数据
    print("\n[Step 1] 数据初始化...")
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    print(f"  当前数据量: {len(records)} 期")
    
    # Step 2: 深度回测(多窗口: 50, 100, 200期)
    print("\n[Step 2] 深度回测验证...")
    runner = BacktestRunner(game_key)
    
    results_by_window = {}
    for window in [50, 100, 200]:
        if len(records) >= window + 10:
            bt = runner.run_backtest(records, window=window)
            results_by_window[window] = bt["avoid_stats"]
            print(f"\n  ── {window}期回测 ──")
            for level in TOP_N_LEVELS:
                stats = bt["avoid_stats"][level]
                beat = "✅" if stats["beat_baseline"] else "❌"
                print(f"    {beat} Top{level}: {stats['hit_rate']:.2%} | 基线={stats['random_baseline']:.2%} | margin={stats['margin']:+.2f}%")
    
    # Step 3: 自动学习优化(如果Top10未跑赢基线)
    print("\n[Step 3] 自动学习优化...")
    # 检查是否需要优化(Top10命中率低于基线)
    best_window = 100
    if best_window in results_by_window:
        top10_stats = results_by_window[best_window][10]
        need_optimize = not top10_stats["beat_baseline"]
        
        if need_optimize:
            print("  ⚠️ Top10命中率低于基线，启动权重优化...")
            optimizer = WeightOptimizer(game_key)
            best_weights, best_metrics = optimizer.optimize_weights(records)
            
            # 更新config.py中的权重
            print(f"  最优权重: {best_weights}")
            print(f"  Top10命中率: {best_metrics['avoid_stats'][10]['hit_rate']:.2%}")
            
            # 写入权重到config
            config_path = PROJECT_ROOT / "config.py"
            with open(config_path, "r") as f:
                config_content = f.read()
            
            # 更新ENGINE_WEIGHTS
            old_weights_str = json.dumps(ENGINE_WEIGHTS["fantasy5"], indent=4)
            new_weights_str = json.dumps(best_weights, indent=4)
            config_content = config_content.replace(old_weights_str, new_weights_str)
            
            with open(config_path, "w") as f:
                f.write(config_content)
            print("  ✅ 权重已更新到config.py")
        else:
            print("  ✅ Top10命中率跑赢基线，当前权重无需优化")
    
    # Step 4: 生成深度回测报告
    print("\n[Step 4] 生成深度回测报告...")
    formatter = ReportFormatter(game_key)
    report = formatter.format_full_report(records)
    
    # Step 5: 保存深度回测结果
    deep_bt = {
        "date": records[-1]["date"] if records else "unknown",
        "data_count": len(records),
        "results_by_window": {
            str(w): {
                str(level): {
                    "hit_rate": results_by_window[w][level]["hit_rate"],
                    "random_baseline": results_by_window[w][level]["random_baseline"],
                    "margin": results_by_window[w][level]["margin"],
                    "beat_baseline": results_by_window[w][level]["beat_baseline"],
                }
                for level in TOP_N_LEVELS
            }
            for w in results_by_window
        },
        "weights": ENGINE_WEIGHTS.get(game_key, {}),
        "optimized": need_optimize if best_window in results_by_window else False,
    }
    deep_path = PROJECT_ROOT / "data" / "fantasy5" / "weekly_deep_backtest.json"
    with open(deep_path, "w", encoding="utf-8") as f:
        json.dump(deep_bt, f, ensure_ascii=False, indent=2)
    print(f"  深度回测结果已保存: {deep_path}")
    
    print("\n" + "=" * 60)
    print("每周深度回测 + 自动学习优化完成 ✅")
    print("=" * 60)


if __name__ == "__main__":
    weekly_deep_backtest()
