"""
🔴 避开模式策略 - 找出最不可能出现的号码，用于排除
"""

from typing import Dict, List, Tuple
from config import STRATEGY_CONFIG, TOP_N_LEVELS
from engines.engine_fusion import EngineFusion


class AvoidMode:
    """避开模式: 融合概率最高的号码 = 最不可能出现"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.fusion = EngineFusion(game_key)
        self.cfg = STRATEGY_CONFIG["avoid"]

    def predict(self, records: List[Dict] = None) -> Dict:
        """
        避开模式预测

        返回: {
            "top2": [...],
            "top4": [...],
            "top10": [...],
            "strategy": "avoid",
            "description": "...",
        }
        """
        result = {
            "strategy": "avoid",
            "emoji": self.cfg["emoji"],
            "name": self.cfg["name"],
            "description": self.cfg["description"],
        }

        for level in TOP_N_LEVELS:
            top = self.fusion.get_top_n_avoid(level, records)
            result[f"top{level}"] = top

        return result

    def format_top_numbers(self, top_list: List[Tuple[int, float, Dict]]) -> str:
        """格式化TopN号码列表"""
        parts = []
        for num, p_low, detail in top_list:
            parts.append(f"{num}({p_low:.3f})")
        return " → ".join(parts)
