"""
TopN选择器 - 从融合概率中提取Top2/4/10
"""

from typing import Dict, List, Tuple
from config import TOP_N_LEVELS


class TopNSelector:
    """TopN号码选择器"""

    def __init__(self, levels: List[int] = None):
        self.levels = levels or TOP_N_LEVELS

    def select(self, ranking: List[Tuple[int, float]], details: Dict[int, Dict] = None) -> Dict[int, List]:
        """
        从排名列表中选择TopN

        ranking: [(number, probability), ...] 已排序
        details: {number: {详细数据}} 可选

        返回: {2: [...], 4: [...], 10: [...]}
        """
        result = {}
        for level in self.levels:
            top = ranking[:level]
            if details:
                enriched = []
                for num, prob in top:
                    enriched.append((num, prob, details.get(num, {})))
                result[level] = enriched
            else:
                result[level] = top

        return result

    def format_simple(self, top_list: List[Tuple[int, float]]) -> str:
        """简单格式: 号码 → 号码"""
        nums = [str(item[0]) for item in top_list]
        return " → ".join(nums)

    def format_with_prob(self, top_list: List[Tuple[int, float]]) -> str:
        """带概率格式: 号码(概率) → 号码(概率)"""
        parts = [f"{item[0]}({item[1]:.3f})" for item in top_list]
        return " → ".join(parts)

    def format_with_detail(self, top_list: List[Tuple[int, float, Dict]]) -> str:
        """带详情格式: 号码(概率) | z=... | bayesian=..."""
        lines = []
        for num, prob, detail in top_list:
            z_score = detail.get("z_score", detail.get("p_low_freq", "?"))
            bayesian = detail.get("p_low_bayesian", "?")
            lines.append(f"  {num:>2} | P_low={prob:.4f} | Z={z_score} | Bay={bayesian}")
        return "\n".join(lines)
