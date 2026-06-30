"""
🟢 回补模式策略 - 冷号即将回补，用于捕捉
"""

from typing import Dict, List, Tuple
from config import STRATEGY_CONFIG, TOP_N_LEVELS
from engines.engine_fusion import EngineFusion


class ReboundMode:
    """回补模式: 冷号加分 → 可能即将回补"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.fusion = EngineFusion(game_key)
        self.cfg = STRATEGY_CONFIG["rebound"]

    def predict(self, records: List[Dict] = None) -> Dict:
        """
        回补模式预测

        返回: {
            "top2": [...],
            "top4": [...],
            "top10": [...],
            "strategy": "rebound",
            "description": "...",
        }
        """
        result = {
            "strategy": "rebound",
            "emoji": self.cfg["emoji"],
            "name": self.cfg["name"],
            "description": self.cfg["description"],
            "params": {
                "rebound_bonus_per_draw": self.cfg["rebound_bonus_per_draw"],
                "recent_window": self.cfg["recent_window"],
            },
        }

        for level in TOP_N_LEVELS:
            top = self.fusion.get_top_n_rebound(level, records)
            result[f"top{level}"] = top

        return result

    def format_top_numbers(self, top_list: List[Tuple[int, float, Dict]]) -> str:
        """格式化TopN号码列表(含间隔信息)"""
        parts = []
        for num, p_low, detail in top_list:
            gap = detail.get("gap", "?")
            parts.append(f"{num}(近{gap}期未出,+{detail.get('gap_bonus', 0):.3f})")
        return " → ".join(parts)
