"""
E1: 频次偏差引擎
核心算法: 历史频次 vs 理论期望 → Z-score偏差 → P_low概率映射
"""

import math
from typing import Dict, List, Tuple

from config import GAMES, get_game_config, get_number_pool
from data.processor import DataProcessor


class FrequencyEngine:
    """频次偏差引擎 - 计算每个号码的历史出现偏差"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.processor = DataProcessor(game_key)
        self.pool = get_number_pool(game_key)

        # Fantasy 5参数
        self.m = self.cfg["draw_count"]  # 每期开出数 = 5
        self.K = len(self.pool)           # 号码池大小 = 39
        self.theoretical_prob = self.m / self.K  # ≈ 0.1282

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        计算频次偏差

        返回: {
            number: {
                "observed_freq": int,    # 实际出现次数
                "expected_freq": float,  # 理论期望次数
                "z_score": float,        # Z-score偏差
                "p_appear": float,       # 预测出现概率
                "p_low": float,          # 预测不出现概率(核心输出)
                "deviation_pct": float,  # 偏差百分比
            }
        }
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records:
            return {}

        freq = self.processor.build_frequency_table(records)
        N = len(records)  # 总期数

        # 理论期望
        expected = N * self.theoretical_prob

        # 标准差
        sigma = math.sqrt(N * self.theoretical_prob * (1 - self.theoretical_prob))

        results = {}
        for n in self.pool:
            observed = freq.get(n, 0)
            z = (observed - expected) / sigma if sigma > 0 else 0

            # P_appear = Φ(z) 映射: Z越高 → 出现越多 → P_appear越高
            # P_low = 1 - P_appear
            p_appear = self._z_to_prob(z)
            p_low = 1 - p_appear

            results[n] = {
                "observed_freq": observed,
                "expected_freq": round(expected, 2),
                "z_score": round(z, 4),
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "deviation_pct": round((observed - expected) / expected * 100, 2) if expected > 0 else 0,
            }

        return results

    def compute_recent(self, window: int = 30) -> Dict[int, Dict]:
        """最近N期的频次偏差(短期趋势)"""
        records = self.processor.fetcher.get_recent_draws(window)
        return self.compute(records)

    def compute_sliding(self, window_sizes: List[int] = [30, 60, 100]) -> Dict[int, Dict]:
        """
        滑动窗口频次偏差 - 多窗口融合
        近期权重更高
        """
        all_results = {}
        weights = {30: 0.4, 60: 0.3, 100: 0.3}  # 近期权重高

        for w in window_sizes:
            results = self.compute_recent(w)
            for n in self.pool:
                if n not in all_results:
                    all_results[n] = {"p_low_weighted": 0}
                all_results[n]["p_low_weighted"] += results[n]["p_low"] * weights.get(w, 0.3)

        return all_results

    def get_ranking(self, records: List[Dict] = None, ascending: bool = True) -> List[Tuple[int, float]]:
        """
        按P_low排序号码
        ascending=True: P_low最低→最高(最不可能出现→最可能出现)
        ascending=False: P_low最高→最低(最可能出现→最不可能出现)
        """
        results = self.compute(records)
        ranking = [(n, results[n]["p_low"]) for n in self.pool]
        ranking.sort(key=lambda x: x[1], reverse=not ascending)
        return ranking

    def get_top_n(self, n: int = 10, records: List[Dict] = None) -> List[Tuple[int, float, Dict]]:
        """获取TopN概率最低号码(含详情)"""
        results = self.compute(records)
        # 按P_low排序: P_low越高 → 号码越不可能出现 → 排越前
        ranking = sorted(self.pool, key=lambda x: results[x]["p_low"], reverse=True)
        top = ranking[:n]
        return [(num, results[num]["p_low"], results[num]) for num in top]

    def _z_to_prob(self, z: float) -> float:
        """
        Z-score → 概率映射 (近似标准正态CDF)
        使用误差函数近似
        """
        # Φ(z) = 0.5 * (1 + erf(z / sqrt(2)))
        try:
            p = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        except (OverflowError, ValueError):
            p = 0.9999 if z > 5 else 0.0001

        # 限制在合理范围内
        # Fantasy 5 理论概率 ≈ 0.1282, 不应该偏离太多
        baseline = self.theoretical_prob
        p = max(baseline * 0.3, min(baseline * 3.0, p))  # 30%~300%的理论值

        return p

    def get_engine_name(self) -> str:
        return "E1频次偏差"

    def get_engine_id(self) -> str:
        return "freq"
