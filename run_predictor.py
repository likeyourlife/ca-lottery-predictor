"""
CLI入口 - 加州天天乐彩票预测分析
可直接运行: python run_predictor.py
"""

import sys
import json
from pathlib import Path

# 添加项目根到sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 修改导入为绝对导入(从项目根开始)
from config import GAMES, DEFAULT_GAME, CONFIDENCE_LABEL, DISCLAIMER, TOP_N_LEVELS
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from engines.engine_freq import FrequencyEngine
from engines.engine_bayesian import BayesianEngine
from engines.engine_markov import MarkovEngine
from engines.engine_consecutive import ConsecutiveEngine
from engines.engine_fft import FFTEngine
from engines.engine_monte_carlo import MonteCarloEngine
from engines.engine_fusion import EngineFusion
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
from output.topn_selector import TopNSelector
from output.report_formatter import ReportFormatter
from backtest.backtest_runner import BacktestRunner, run_backtest_cli
from backtest.weight_optimizer import WeightOptimizer, run_optimize_cli


def main(game_key: str = DEFAULT_GAME, mode: str = "full"):
    """
    主入口函数

    game_key: fantasy5 / daily3 / daily4
    mode: full / json / quick / backtest / backtest_e1e2 / optimize
    """
    # 初始化数据
    if game_key == "fantasy5":
        fetcher = init_fantasy5_data()
    else:
        fetcher = DataFetcher(game_key)

    records = fetcher.get_all_draws()
    if not records:
        print("❌ 无历史数据，请先更新数据")
        return

    print(f"📊 数据量: {len(records)} 期")

    if mode == "backtest":
        # 5引擎回测
        run_backtest_cli(game_key, window=100, engines="e1_e5")
        return
    elif mode == "backtest_e1e2":
        # 仅E1+E2回测
        run_backtest_cli(game_key, window=100, engines="e1_e2")
        return
    elif mode == "optimize":
        # 权重动态调优
        run_optimize_cli(game_key)
        return

    print(f"📊 数据量: {len(records)} 期")

    # 生成报告
    formatter = ReportFormatter(game_key)

    if mode == "full":
        report = formatter.format_full_report(records)
        print(report)
    elif mode == "json":
        json_report = formatter.format_json_report(records)
        print(json.dumps(json_report, ensure_ascii=False, indent=2))
    elif mode == "quick":
        # 快速模式: 只输出避开Top10
        avoid = AvoidMode(game_key)
        result = avoid.predict(records)
        for level in TOP_N_LEVELS:
            top = result.get(f"top{level}", [])
            nums = " → ".join([str(t[0]) for t in top])
            print(f"🔴 避开 Top{level}: {nums}")

        rebound = ReboundMode(game_key)
        result = rebound.predict(records)
        for level in TOP_N_LEVELS:
            top = result.get(f"top{level}", [])
            nums = " → ".join([str(t[0]) for t in top])
            print(f"🟢 回补 Top{level}: {nums}")
    else:
        print(f"未知模式: {mode}")


if __name__ == "__main__":
    game = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAME
    mode = sys.argv[2] if len(sys.argv) > 2 else "full"
    main(game, mode)
