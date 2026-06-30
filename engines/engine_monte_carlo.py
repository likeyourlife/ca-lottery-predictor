"""
蒙特卡洛引擎E6 - 随机排除 + 统计偏差叠加
核心思想: 通过模拟N次随机排除过程, 估算每个号码的偏差敏感性

方法:
1. 纯随机基线: N次随机选Top10号码, 计算每个号码被选中的频率(理论≈10/39)
2. 偏差叠加: 在随机基础上, 给"冷号"(历史频次低)额外概率扰动
3. 偏差敏感性 = 带偏差的选中频率 - 纯随机选中频率
4. 敏感性越高 → 该号码越容易被偏差信号影响 → P_low越高

输出: 每个号码的 P_low(蒙特卡洛偏差概率)
"""

import random
from typing import Dict, List, Tuple
from config import GAMES, get_game_config, get_number_pool
from data.processor import DataProcessor


class MonteCarloEngine:
    """蒙特卡洛模拟引擎 - 偏差敏感性分析"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.pool = get_number_pool(game_key)
        self.K = len(self.pool)  # 39
        self.m = self.cfg["draw_count"]  # 5
        self.processor = DataProcessor(game_key)

        # 模拟参数
        self.n_simulations = 1000   # 模拟次数(回测时降低以提速)
        self.bias_strength = 0.15   # 偏差扰动强度(0=纯随机, 1=完全由偏差决定)

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        蒙特卡洛模拟计算

        Returns: {number: {"p_low_mc": float, "bias_sensitivity": float, "random_freq": float, "biased_freq": float, ...}}
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        # ── 1. 计算频次偏差 ──
        freq_table = self.processor.build_frequency_table(records)
        n_draws = len(records)

        # 每个号码的理论期望频次
        expected_freq = n_draws * self.cfg["theoretical_prob"]  # ≈ n * 5/39

        # 频次偏差率: (实际-期望)/期望 → 越低=越冷号
        freq_deviation = {}
        for n in self.pool:
            actual = freq_table.get(n, 0)
            dev = (actual - expected_freq) / expected_freq if expected_freq > 0 else 0
            freq_deviation[n] = dev

        # ── 2. 纯随机基线 ──
        # 模拟N次: 随机选10个号码作为"排除列表"
        random_selection_counts = {n: 0 for n in self.pool}

        for _ in range(self.n_simulations):
            # 随机选10个号码
            selected = random.sample(self.pool, 10)
            for n in selected:
                random_selection_counts[n] += 1

        random_freq = {n: random_selection_counts[n] / self.n_simulations for n in self.pool}

        # ── 3. 带偏差的模拟 ──
        # 给冷号额外选中概率: 选中权重 = 1 + bias_strength * (-freq_deviation)
        # 频次偏差越低(冷号) → 权重越高 → 更容易被选中到排除列表
        biased_selection_counts = {n: 0 for n in self.pool}

        for _ in range(self.n_simulations):
            # 计算每个号码的选中权重
            weights = []
            for n in self.pool:
                dev = freq_deviation[n]
                # 冷号(dev<0) → 权重增加, 热号(dev>0) → 权重减少
                w = 1.0 + self.bias_strength * (-dev)
                # 确保权重>0
                w = max(w, 0.1)
                weights.append(w)

            # 加权随机选10个号码
            total_w = sum(weights)
            probs = [w / total_w for w in weights]

            # 用random.choices做加权选择(不重复)
            selected = []
            remaining_pool = list(self.pool)
            remaining_probs = list(probs)

            for _ in range(10):
                if not remaining_pool:
                    break
                # 加权选一个
                chosen = random.choices(remaining_pool, weights=remaining_probs, k=1)[0]
                selected.append(chosen)
                # 移除已选
                idx = remaining_pool.index(chosen)
                remaining_pool.pop(idx)
                remaining_probs.pop(idx)

            for n in selected:
                biased_selection_counts[n] += 1

        biased_freq = {n: biased_selection_counts[n] / self.n_simulations for n in self.pool}

        # ── 4. 偏差敏感性 ──
        # sensitivity = biased_freq - random_freq
        # 正值 → 该号码在偏差驱动下更容易被排除 → P_low更高
        sensitivity = {n: biased_freq[n] - random_freq[n] for n in self.pool}

        # ── 5. 转换为P_low ──
        # P_low_mc = 理论P_low + sensitivity的映射
        # sensitivity范围大约 [-0.05, +0.05], 需要映射到P_low的微调范围
        # 用线性映射: P_low_mc = theoretical_low_prob + sensitivity * scale_factor
        theoretical_low = self.cfg["theoretical_low_prob"]  # ≈ 0.8718

        # scale_factor: 让最大sensitivity映射到±0.05的P_low偏移
        max_sens = max(abs(s) for s in sensitivity.values()) if sensitivity else 0.01
        scale_factor = 0.05 / max_sens if max_sens > 0 else 1.0

        results = {}
        for n in self.pool:
            p_low_mc = theoretical_low + sensitivity[n] * scale_factor
            # 确保在合理范围 [0.8, 1.0]
            p_low_mc = max(0.80, min(1.00, p_low_mc))

            results[n] = {
                "p_low": round(p_low_mc, 4),
                "p_appear": round(1 - p_low_mc, 4),
                "engine_id": "monte_carlo",
                "bias_sensitivity": round(sensitivity[n], 4),
                "random_freq": round(random_freq[n], 4),
                "biased_freq": round(biased_freq[n], 4),
                "freq_deviation": round(freq_deviation[n], 4),
                "n_simulations": self.n_simulations,
            }

        return results

    def get_engine_name(self) -> str:
        return "蒙特卡洛偏差模拟"

    def get_engine_id(self) -> str:
        return "monte_carlo"
