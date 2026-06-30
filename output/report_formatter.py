"""
报告格式化模块 - 终端/文本报告输出
支持6引擎(E1-E6)融合报告
"""

from datetime import datetime
from typing import Dict, List

from config import (
    GAMES, CONFIDENCE_LABEL, DISCLAIMER, STRATEGY_CONFIG,
    TOP_N_LEVELS, DEFAULT_GAME, ENGINE_WEIGHTS
)
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
from output.topn_selector import TopNSelector


class ReportFormatter:
    """预测报告格式化器 - 6引擎版本"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = GAMES[game_key]
        self.avoid = AvoidMode(game_key)
        self.rebound = ReboundMode(game_key)
        self.selector = TopNSelector()
        self.weights = ENGINE_WEIGHTS.get(game_key, {})

    def format_full_report(self, records: List[Dict] = None) -> str:
        """
        生成完整预测报告(终端格式)
        """
        # 获取数据
        avoid_result = self.avoid.predict(records)
        rebound_result = self.rebound.predict(records)

        # 下一期日期
        from data.processor import DataProcessor
        processor = DataProcessor(self.game_key)
        if records is None:
            records = processor.fetcher.get_all_draws()
        last_date = processor.fetcher.get_last_draw_date()

        # 引擎诊断信息
        from engines.engine_fusion import EngineFusion
        fusion = EngineFusion(self.game_key)
        report_data = fusion.get_full_report(records)
        diagnosis = report_data.get("engine_diagnosis", {})

        # 构建报告
        lines = []
        lines.append("╔" + "═" * 58 + "╗")
        lines.append(f"║  🍡 加州天天乐预测报告 | {self.cfg['name']} | 下一期预测       ║")
        lines.append(f"║  号码空间: 1-39 | 每期开出: 5个 | 融合引擎: E1→E6       ║")
        lines.append("╠" + "═" * 58 + "╣")
        lines.append("")
        lines.append(f"  📊 最新一期: {last_date}")
        lines.append(f"  📊 历史数据: {len(records)}期")

        # 引擎权重
        weight_str = " | ".join([
            f"E1(频次)={self.weights.get('freq', 0):.0%}",
            f"E2(贝叶斯)={self.weights.get('bayesian', 0):.0%}",
            f"E3(马尔可夫)={self.weights.get('markov', 0):.0%}",
        ])
        lines.append(f"  📊 权重: {weight_str}")
        weight_str2 = " | ".join([
            f"E4(联合)={self.weights.get('joint', 0):.0%}",
            f"E5(FFT)={self.weights.get('fft', 0):.0%}",
            f"E6(MC)={self.weights.get('monte_carlo', 0):.0%}",
        ])
        lines.append(f"  📊       {weight_str2}")
        lines.append("")

        # 🔴 避开模式
        lines.append("  ── 🔴 避开模式 (最不可能出现的号码) ──")
        for level in TOP_N_LEVELS:
            top = avoid_result.get(f"top{level}", [])
            if top:
                nums_str = self.selector.format_with_prob(top)
                lines.append(f"  🔴 Top{level}: {nums_str}")
        lines.append("")

        # 🟢 回补模式
        lines.append("  ── 🟢 回补模式 (冷号可能回补) ──")
        for level in TOP_N_LEVELS:
            top = rebound_result.get(f"top{level}", [])
            if top:
                nums_str = self.rebound.format_top_numbers(top)
                lines.append(f"  🟢 Top{level}: {nums_str}")
        lines.append("")

        # 引擎诊断
        lines.append("  ── 🔬 引擎诊断 ──")
        if "markov" in diagnosis:
            md = diagnosis["markov"]
            lines.append(f"  E3 马尔可夫: hot={md['hot_count']} cold={md['cold_count']} neutral={md['neutral_count']}")
        if "fft" in diagnosis:
            fd = diagnosis["fft"]
            lines.append(f"  E5 FFT周期: peak={fd['peak_count']} valley={fd['valley_count']} transition={fd['transition_count']}")
        if "joint" in diagnosis:
            jd = diagnosis["joint"]
            lines.append(f"  E4 连号联合: 排斥主导={jd['exclusion_dominant']} 共现主导={jd['co_occurrence_dominant']}")
        if "monte_carlo" in diagnosis:
            mc = diagnosis["monte_carlo"]
            lines.append(f"  E6 蒙特卡洛: 正偏差={mc['positive_sensitivity']} 负偏差={mc['negative_sensitivity']} 近零={mc['near_zero']}")

        lines.append("")
        lines.append(f"  📊 理论基线: P_low = {self.cfg['theoretical_low_prob']:.4f} ({self.cfg['theoretical_low_prob']*100:.2f}%)")
        lines.append(f"  📊 置信度: {CONFIDENCE_LABEL}")
        lines.append("╚" + "═" * 58 + "╝")
        lines.append("")
        lines.append(f"⚠️ {DISCLAIMER}")

        return "\n".join(lines)

    def format_json_report(self, records: List[Dict] = None) -> Dict:
        """生成JSON格式报告(供程序调用)"""
        avoid_result = self.avoid.predict(records)
        rebound_result = self.rebound.predict(records)

        from engines.engine_fusion import EngineFusion
        fusion = EngineFusion(self.game_key)
        report_data = fusion.get_full_report(records)

        return {
            "report_time": datetime.now().isoformat(),
            "game": self.cfg["name"],
            "game_key": self.game_key,
            "number_range": self.cfg["number_range"],
            "draw_count": self.cfg["draw_count"],
            "theoretical_prob": self.cfg["theoretical_prob"],
            "theoretical_low_prob": self.cfg["theoretical_low_prob"],
            "engine_weights": self.weights,
            "engine_diagnosis": report_data.get("engine_diagnosis", {}),
            "avoid": {
                "strategy": "avoid",
                "results": {
                    f"top{level}": [
                        {"number": num, "p_low": prob}
                        for num, prob, _ in avoid_result.get(f"top{level}", [])
                    ]
                    for level in TOP_N_LEVELS
                },
            },
            "rebound": {
                "strategy": "rebound",
                "results": {
                    f"top{level}": [
                        {"number": num, "p_low": prob, "gap": detail.get("gap", 0)}
                        for num, prob, detail in rebound_result.get(f"top{level}", [])
                    ]
                    for level in TOP_N_LEVELS
                },
            },
            "confidence": CONFIDENCE_LABEL,
            "disclaimer": DISCLAIMER,
        }
