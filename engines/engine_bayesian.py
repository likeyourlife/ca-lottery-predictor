"""
E2: 贝叶斯概率引擎
核心算法: Beta-Binomial后验更新
先验: 理论概率 Beta(α₀, β₀) 而非均匀先验
后验: Beta(α₀+k, β₀+N-k)
"""

import math
from typing import Dict, List, Tuple

from config import GAMES, get_game_config, get_number_pool, BAYESIAN_CONFIG
from data.processor import DataProcessor


class BayesianEngine:
    """贝叶斯概率引擎 - Beta-Binomial后验推断"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.processor = DataProcessor(game_key)
        self.pool = get_number_pool(game_key)

        # Fantasy 5 参数
        self.m = self.cfg["draw_count"]  # 5
        self.K = len(self.pool)           # 39
        self.theoretical_prob = self.m / self.K  # ≈ 0.1282

        # 贝叶斯先验参数
        bay_cfg = BAYESIAN_CONFIG.get(game_key, {})
        prior_weight = bay_cfg.get("prior_weight", 50)
        self.alpha0 = self.theoretical_prob * prior_weight   # ≈ 6.41
        self.beta0 = (1 - self.theoretical_prob) * prior_weight  # ≈ 43.59

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        计算贝叶斯后验概率

        返回: {
            number: {
                "k": int,           # 观测出现次数
                "alpha_post": float, # 后验α
                "beta_post": float,  # 后验β
                "p_appear": float,   # 后验出现概率(均值)
                "p_low": float,      # 后验不出现概率
                "credible_lower": float, # 95%可信区间下界
                "credible_upper": float, # 95%可信区间上界
            }
        }
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records:
            return {}

        freq = self.processor.build_frequency_table(records)
        N = len(records)

        results = {}
        for n in self.pool:
            k = freq.get(n, 0)

            # 后验参数
            alpha_post = self.alpha0 + k
            beta_post = self.beta0 + (N - k)

            # 后验均值 = P(号i出现)
            p_appear = alpha_post / (alpha_post + beta_post)
            p_low = 1 - p_appear

            # 95%可信区间 (Beta分布)
            lower = self._beta_ci_lower(alpha_post, beta_post)
            upper = self._beta_ci_upper(alpha_post, beta_post)

            results[n] = {
                "k": k,
                "alpha_post": round(alpha_post, 4),
                "beta_post": round(beta_post, 4),
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "credible_lower": round(lower, 4),
                "credible_upper": round(upper, 4),
            }

        return results

    def compute_recent(self, window: int = 30) -> Dict[int, Dict]:
        """最近N期贝叶斯更新"""
        records = self.processor.fetcher.get_recent_draws(window)
        return self.compute(records)

    def compute_incremental(self, prior_alpha: Dict[int, float],
                           prior_beta: Dict[int, float],
                           new_records: List[Dict]) -> Dict[int, Dict]:
        """
        增量贝叶斯更新 - 不需要重新计算全量
        """
        freq_new = self.processor.build_frequency_table(new_records)
        N_new = len(new_records)

        results = {}
        for n in self.pool:
            k_new = freq_new.get(n, 0)
            alpha_post = prior_alpha.get(n, self.alpha0) + k_new
            beta_post = prior_beta.get(n, self.beta0) + (N_new - k_new)

            p_appear = alpha_post / (alpha_post + beta_post)
            p_low = 1 - p_appear

            results[n] = {
                "k": k_new,
                "alpha_post": round(alpha_post, 4),
                "beta_post": round(beta_post, 4),
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
            }

        return results

    def get_top_n(self, n: int = 10, records: List[Dict] = None) -> List[Tuple[int, float, Dict]]:
        """获取TopN概率最低号码(含详情)"""
        results = self.compute(records)
        ranking = sorted(self.pool, key=lambda x: results[x]["p_low"], reverse=True)
        top = ranking[:n]
        return [(num, results[num]["p_low"], results[num]) for num in top]

    def get_ranking(self, records: List[Dict] = None) -> List[Tuple[int, float]]:
        """按P_low排序"""
        results = self.compute(records)
        ranking = [(n, results[n]["p_low"]) for n in self.pool]
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def _beta_ci_lower(self, alpha: float, beta: float) -> float:
        """Beta分布95%可信区间下界(近似)"""
        # 使用正态近似: μ = α/(α+β), σ² = αβ/((α+β)²(α+β+1))
        total = alpha + beta
        if total <= 0:
            return 0
        mean = alpha / total
        var = alpha * beta / (total * total * (total + 1)) if total > 0 else 0
        std = math.sqrt(var) if var > 0 else 0
        lower = max(0, mean - 1.96 * std)
        return lower

    def _beta_ci_upper(self, alpha: float, beta: float) -> float:
        """Beta分布95%可信区间上界(近似)"""
        total = alpha + beta
        if total <= 0:
            return 1
        mean = alpha / total
        var = alpha * beta / (total * total * (total + 1)) if total > 0 else 0
        std = math.sqrt(var) if var > 0 else 0
        upper = min(1, mean + 1.96 * std)
        return upper

    def get_engine_name(self) -> str:
        return "E2贝叶斯概率"

    def get_engine_id(self) -> str:
        return "bayesian"
