"""
E3: 马尔可夫链引擎
核心算法: 一阶马尔可夫状态转移概率矩阵
状态: 号码i是否出现在上期 (出现/不出现 → 2态)
转移: P(i出现|上期出现) vs P(i出现|上期未出现)
输出: P_low(i) = 1 - P(i下期出现)
"""

import math
from typing import Dict, List, Tuple

from config import GAMES, get_game_config, get_number_pool
from data.processor import DataProcessor


class MarkovEngine:
    """马尔可夫链引擎 - 一阶状态转移概率"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.processor = DataProcessor(game_key)
        self.pool = get_number_pool(game_key)

        self.m = self.cfg["draw_count"]   # 每期开出数 = 5
        self.K = len(self.pool)            # 号码池大小 = 39
        self.theoretical_prob = self.m / self.K  # ≈ 0.1282
        self.theoretical_low_prob = 1 - self.theoretical_prob

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        计算马尔可夫链转移概率

        返回: {
            number: {
                "transition_appear_after_appear": float,  # P(出现|上期出现)
                "transition_appear_after_miss": float,    # P(出现|上期未出现)
                "count_aa": int,   # 上期出现→本期出现次数
                "count_am": int,   # 上期出现→本期未出现次数
                "count_ma": int,   # 上期未出现→本期出现次数
                "count_mm": int,   # 上期未出现→本期未出现次数
                "last_state": str, # 上期状态 "appear"/"miss"
                "p_appear": float, # 预测出现概率(基于上期状态)
                "p_low": float,    # 预测不出现概率(核心输出)
                "markov_signal": str,  # 信号类型: "hot"/"cold"/"neutral"
            }
        }
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records or len(records) < 3:
            return self._default_results()

        # 构建出现序列
        presence = self.processor.build_presence_series(records)
        N = len(records)

        # 上一期号码
        last_numbers = self.processor.extract_numbers_from_record(records[-1])
        last_set = set(last_numbers)

        results = {}
        for n in self.pool:
            series = presence[n]

            # 统计转移次数
            aa = 0  # 上期出现→本期出现
            am = 0  # 上期出现→本期未出现
            ma = 0  # 上期未出现→本期出现
            mm = 0  # 上期未出现→本期未出现

            for t in range(1, N):
                prev_state = series[t - 1]  # 上期
                curr_state = series[t]      # 本期

                if prev_state == 1 and curr_state == 1:
                    aa += 1
                elif prev_state == 1 and curr_state == 0:
                    am += 1
                elif prev_state == 0 and curr_state == 1:
                    ma += 1
                else:
                    mm += 1

            # 转移概率 (带平滑: 避免零概率)
            smoothing = 1.0  # Laplace平滑参数

            total_from_appear = aa + am + smoothing * 2
            total_from_miss = ma + mm + smoothing * 2

            p_appear_after_appear = (aa + smoothing) / total_from_appear
            p_appear_after_miss = (ma + smoothing) / total_from_miss

            # 上期状态
            last_state = "appear" if n in last_set else "miss"

            # 预测: 根据上期状态选择转移概率
            if last_state == "appear":
                p_appear = p_appear_after_appear
            else:
                p_appear = p_appear_after_miss

            p_low = 1 - p_appear

            # 信号分类
            # 如果P(出现|上期出现) > 理论概率 → "hot" (连续性倾向)
            # 如果P(出现|上期未出现) < 理论概率 → "cold" (回避倾向)
            markov_signal = "neutral"
            if p_appear_after_appear > self.theoretical_prob * 1.3:
                markov_signal = "hot"  # 号码有连续出现倾向
            elif p_appear_after_miss < self.theoretical_prob * 0.7:
                markov_signal = "cold"  # 号码有回避倾向（上期没出→下期也不出）

            results[n] = {
                "transition_appear_after_appear": round(p_appear_after_appear, 4),
                "transition_appear_after_miss": round(p_appear_after_miss, 4),
                "count_aa": aa,
                "count_am": am,
                "count_ma": ma,
                "count_mm": mm,
                "last_state": last_state,
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "markov_signal": markov_signal,
            }

        return results

    def compute_sliding_markov(self, windows: List[int] = [50, 100, 200]) -> Dict[int, Dict]:
        """
        滑动窗口马尔可夫 - 多窗口融合
        近期窗口权重更高，捕捉短期状态转移变化
        """
        records = self.processor.fetcher.get_all_draws()
        if len(records) < max(windows) + 5:
            return self.compute(records)

        window_weights = {50: 0.5, 100: 0.3, 200: 0.2}

        all_p_low = {}
        for n in self.pool:
            all_p_low[n] = {"p_low_weighted": 0, "markov_signal": "neutral"}

        for w in windows:
            recent = records[-(w + 1):]  # 多取1期作为上期状态
            results = self.compute(recent)
            weight = window_weights.get(w, 0.3)
            for n in self.pool:
                all_p_low[n]["p_low_weighted"] += results[n]["p_low"] * weight

        # 确定信号
        for n in self.pool:
            p = all_p_low[n]["p_low_weighted"]
            if p > self.theoretical_low_prob * 1.05:
                all_p_low[n]["markov_signal"] = "cold"
            elif p < self.theoretical_low_prob * 0.95:
                all_p_low[n]["markov_signal"] = "hot"
            else:
                all_p_low[n]["markov_signal"] = "neutral"

        return all_p_low

    def compute_second_order(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        二阶马尔可夫: 考虑前两期的联合状态
        状态空间: (上上期, 上期) → 4种组合
        (出现,出现), (出现,未出现), (未出现,出现), (未出现,未出现)
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records or len(records) < 4:
            return self._default_results()

        presence = self.processor.build_presence_series(records)
        N = len(records)

        # 上一期和上上期号码
        last_numbers = self.processor.extract_numbers_from_record(records[-1])
        prev_numbers = self.processor.extract_numbers_from_record(records[-2])
        last_set = set(last_numbers)
        prev_set = set(prev_numbers)

        results = {}
        for n in self.pool:
            series = presence[n]

            # 统计二阶转移
            # 状态编码: (t-2状态, t-1状态) → t状态
            transitions = {
                (1, 1): {"appear": 0, "miss": 0},
                (1, 0): {"appear": 0, "miss": 0},
                (0, 1): {"appear": 0, "miss": 0},
                (0, 0): {"appear": 0, "miss": 0},
            }

            for t in range(2, N):
                s2 = series[t - 2]  # 上上期
                s1 = series[t - 1]  # 上期
                s0 = series[t]      # 本期
                state = (s2, s1)
                outcome = "appear" if s0 == 1 else "miss"
                transitions[state][outcome] += 1

            # 当前状态 (上上期, 上期)
            current_prev = 1 if n in prev_set else 0
            current_last = 1 if n in last_set else 0
            current_state = (current_prev, current_last)

            smoothing = 1.0
            total = transitions[current_state]["appear"] + transitions[current_state]["miss"] + smoothing * 2
            p_appear = (transitions[current_state]["appear"] + smoothing) / total
            p_low = 1 - p_appear

            results[n] = {
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "current_state": current_state,
                "transitions": {str(k): v for k, v in transitions.items()},
                "order": 2,
            }

        return results

    def _default_results(self) -> Dict[int, Dict]:
        """数据不足时返回理论基线"""
        results = {}
        for n in self.pool:
            results[n] = {
                "transition_appear_after_appear": round(self.theoretical_prob, 4),
                "transition_appear_after_miss": round(self.theoretical_prob, 4),
                "count_aa": 0, "count_am": 0, "count_ma": 0, "count_mm": 0,
                "last_state": "unknown",
                "p_appear": round(self.theoretical_prob, 4),
                "p_low": round(self.theoretical_low_prob, 4),
                "markov_signal": "neutral",
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
        return "E3马尔可夫链"

    def get_engine_id(self) -> str:
        return "markov"
