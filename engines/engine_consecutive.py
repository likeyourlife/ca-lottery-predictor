"""
E4: 连号联合引擎
核心算法: 号码间共现/排斥模式分析
原理: Fantasy 5每期开出5个号码(不重复), 号码间存在共现倾向和排斥倾向
方法: 计算每对号码的历史共现频次 vs 理论共现期望 → 联合偏差矩阵
输出: P_low(i) 基于号码i与其他号码的联合排斥强度加权
"""

import math
from typing import Dict, List, Tuple
from itertools import combinations

from config import GAMES, get_game_config, get_number_pool
from data.processor import DataProcessor


class ConsecutiveEngine:
    """连号联合引擎 - 共现/排斥模式分析"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.processor = DataProcessor(game_key)
        self.pool = get_number_pool(game_key)

        self.m = self.cfg["draw_count"]   # 每期开出数 = 5
        self.K = len(self.pool)            # 号码池大小 = 39
        self.theoretical_prob = self.m / self.K

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        计算连号联合概率

        逻辑:
        1. 统计每对号码(i,j)的历史共现次数
        2. 计算理论共现期望 = P(i出现 AND j出现)
           = C(K-2, m-2) / C(K, m) (i,j都出现)
           = 对于Fantasy5: C(37,3)/C(39,5) = 0.1282 * (5-1)/(39-1) ≈ 0.01334
        3. 计算排斥偏差: 实际共现 - 期望共现
        4. 对每个号码i, 综合所有与i相关的排斥偏差 → P_low(i)

        返回: {
            number: {
                "co_occurrence_score": float,    # 共现正向得分(被其他号吸引)
                "exclusion_score": float,        # 排斥反向得分(被其他号排斥)
                "joint_p_low": float,            # 联合P_low(核心输出)
                "strongest_exclusion": Tuple,     # 最强排斥号码对
                "strongest_co_occurrence": Tuple, # 最强共现号码对
                "p_appear": float,
                "p_low": float,
            }
        }
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records or len(records) < 20:
            return self._default_results()

        N = len(records)

        # ── 1. 统计共现矩阵 ──
        co_matrix = self._build_co_occurrence_matrix(records)

        # ── 2. 计算理论共现期望 ──
        # P(i AND j) = C(K-2, m-2) / C(K, m)
        # 简化: = (m/K) * ((m-1)/(K-1))
        expected_co_prob = self.theoretical_prob * ((self.m - 1) / (self.K - 1))
        expected_co_count = N * expected_co_prob

        # ── 3. 计算每对号码的偏差 ──
        pair_deviation = {}
        for i in self.pool:
            for j in self.pool:
                if i < j:
                    actual = co_matrix.get((i, j), 0)
                    deviation = (actual - expected_co_count) / max(expected_co_count, 1)
                    pair_deviation[(i, j)] = {
                        "actual": actual,
                        "expected": round(expected_co_count, 2),
                        "deviation": round(deviation, 4),
                    }

        # ── 4. 对每个号码综合偏差 ──
        results = {}
        for n in self.pool:
            exclusion_score = 0  # 被排斥: 其他号码不愿与n同台
            co_occurrence_score = 0  # 被吸引: 其他号码喜欢与n同台
            max_exclusion = (0, 0, 0)  # (partner, deviation, actual)
            max_co_occurrence = (0, 0, 0)

            for other in self.pool:
                if other == n:
                    continue
                key = (min(n, other), max(n, other))
                dev = pair_deviation.get(key, {}).get("deviation", 0)

                if dev < 0:  # 排斥: 实际共现低于期望
                    # 排斥强度: deviation越负, 排斥越强
                    exclusion_score += abs(dev)
                    if abs(dev) > max_exclusion[1]:
                        max_exclusion = (other, abs(dev), pair_deviation[key]["actual"])
                else:  # 共现: 实际共现高于期望
                    co_occurrence_score += dev
                    if dev > max_co_occurrence[1]:
                        max_co_occurrence = (other, dev, pair_deviation[key]["actual"])

            # 排斥得分越高 → 该号码越"孤立" → 越不容易出现
            # 吸引得分越高 → 该号码越"受欢迎" → 越容易出现
            # 综合信号: 排斥倾向 - 吸引倾向
            joint_signal = exclusion_score - co_occurrence_score

            # P_low映射: 正信号(排斥倾向) → P_low更高
            # 使用sigmoid映射
            p_low_adjustment = self._signal_to_p_low_adjustment(joint_signal)
            p_low = self.cfg["theoretical_low_prob"] + p_low_adjustment
            p_low = max(0.80, min(0.95, p_low))  # 合理范围限制

            p_appear = 1 - p_low

            results[n] = {
                "co_occurrence_score": round(co_occurrence_score, 4),
                "exclusion_score": round(exclusion_score, 4),
                "joint_signal": round(joint_signal, 4),
                "p_low_adjustment": round(p_low_adjustment, 4),
                "joint_p_low": round(p_low, 4),
                "strongest_exclusion": max_exclusion,
                "strongest_co_occurrence": max_co_occurrence,
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
            }

        return results

    def compute_recent(self, window: int = 50) -> Dict[int, Dict]:
        """最近N期的联合偏差"""
        records = self.processor.fetcher.get_recent_draws(window)
        return self.compute(records)

    def _build_co_occurrence_matrix(self, records: List[Dict]) -> Dict[Tuple, int]:
        """构建号码对共现矩阵"""
        co_matrix = {}

        for record in records:
            numbers = self.processor.extract_numbers_from_record(record)
            # 所有号码对的组合
            for pair in combinations(sorted(numbers), 2):
                if pair not in co_matrix:
                    co_matrix[pair] = 0
                co_matrix[pair] += 1

        return co_matrix

    def _signal_to_p_low_adjustment(self, signal: float) -> float:
        """
        联合信号 → P_low调整量
        正信号(排斥倾向) → P_low上调
        负信号(吸引倾向) → P_low下调
        使用tanh映射, 控制调整幅度在[-0.05, 0.05]
        """
        # 归一化信号: 每个号码最多38个对, 平均偏差约1.0
        normalized = signal / 38.0  # 归一化到每个对的平均偏差

        # tanh映射 → 调整量在[-0.05, +0.05]
        adjustment = 0.05 * math.tanh(normalized * 2)

        return adjustment

    def compute_consecutive_pattern(self, records: List[Dict] = None) -> Dict:
        """
        连号模式分析: 检测连续号码(如3-4, 17-18-19)出现频率
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        consecutive_pairs = {n: 0 for n in self.pool}  # 每个号码参与连号的次数
        consecutive_count = 0  # 有连号的期数

        for record in records:
            numbers = sorted(self.processor.extract_numbers_from_record(record))
            has_consecutive = False
            for i in range(len(numbers) - 1):
                if numbers[i + 1] - numbers[i] == 1:
                    has_consecutive = True
                    consecutive_pairs[numbers[i]] += 1
                    consecutive_pairs[numbers[i + 1]] += 1
            if has_consecutive:
                consecutive_count += 1

        N = len(records)
        # 理论: 5个号码中至少有一对连续的概率
        # 简化近似 ≈ 0.47 (经验值)
        consecutive_ratio = consecutive_count / N if N > 0 else 0

        return {
            "total_draws": N,
            "consecutive_draws": consecutive_count,
            "consecutive_ratio": round(consecutive_ratio, 4),
            "consecutive_pairs": consecutive_pairs,
        }

    def _default_results(self) -> Dict[int, Dict]:
        """数据不足时返回理论基线"""
        results = {}
        for n in self.pool:
            results[n] = {
                "co_occurrence_score": 0,
                "exclusion_score": 0,
                "joint_signal": 0,
                "p_low_adjustment": 0,
                "joint_p_low": round(self.cfg["theoretical_low_prob"], 4),
                "strongest_exclusion": (0, 0, 0),
                "strongest_co_occurrence": (0, 0, 0),
                "p_appear": round(self.theoretical_prob, 4),
                "p_low": round(self.cfg["theoretical_low_prob"], 4),
            }
        return results

    def get_ranking(self, records: List[Dict] = None) -> List[Tuple[int, float]]:
        """按P_low排序号码"""
        results = self.compute(records)
        ranking = [(n, results[n]["p_low"]) for n in self.pool]
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def get_top_n(self, n: int = 10, records: List[Dict] = None) -> List[Tuple[int, float, Dict]]:
        """获取TopN概率最低号码"""
        results = self.compute(records)
        ranking = sorted(self.pool, key=lambda x: results[x]["p_low"], reverse=True)
        top = ranking[:n]
        return [(num, results[num]["p_low"], results[num]) for num in top]

    def get_engine_name(self) -> str:
        return "E4连号联合"

    def get_engine_id(self) -> str:
        return "joint"
