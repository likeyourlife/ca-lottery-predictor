"""
引擎融合调度器 - 6引擎加权融合 + 双模式策略
E1频次偏差 + E2贝叶斯 + E3马尔可夫 + E4连号联合 + E5 FFT周期 + E6蒙特卡洛
"""

from typing import Dict, List, Tuple, Optional
from config import ENGINE_WEIGHTS, STRATEGY_CONFIG, TOP_N_LEVELS, get_game_config, get_number_pool
from engines.engine_freq import FrequencyEngine
from engines.engine_bayesian import BayesianEngine
from engines.engine_markov import MarkovEngine
from engines.engine_consecutive import ConsecutiveEngine
from engines.engine_fft import FFTEngine
from engines.engine_monte_carlo import MonteCarloEngine


class EngineFusion:
    """引擎融合调度器 - 6引擎加权融合"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.pool = get_number_pool(game_key)

        # 初始化6引擎
        self.engines = {
            "freq": FrequencyEngine(game_key),
            "bayesian": BayesianEngine(game_key),
            "markov": MarkovEngine(game_key),
            "joint": ConsecutiveEngine(game_key),
            "fft": FFTEngine(game_key),
            "monte_carlo": MonteCarloEngine(game_key),
        }

        # 引擎权重
        self.weights = ENGINE_WEIGHTS.get(game_key, {})

    def compute_fusion(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        6引擎加权融合计算

        返回: {
            number: {
                "p_low_freq": float,
                "p_low_bayesian": float,
                "p_low_markov": float,
                "p_low_joint": float,
                "p_low_fft": float,
                "p_low_monte_carlo": float,
                "p_low_fusion": float,   # 融合P_low
                "p_appear_fusion": float, # 融合P_appear
                ...
            }
        }
        """
        # 各引擎独立计算
        engine_results = {}
        for eid, engine in self.engines.items():
            engine_results[eid] = engine.compute(records)

        # 加权融合
        fusion = {}
        active_weights = {eid: self.weights.get(eid, 0) for eid in self.engines}
        total_weight = sum(active_weights.values())

        for n in self.pool:
            p_low_fusion = 0
            detail = {}

            for eid, engine in self.engines.items():
                w = active_weights.get(eid, 0)
                p_low = engine_results[eid].get(n, {}).get("p_low", self.cfg["theoretical_low_prob"])
                p_low_fusion += w * p_low
                detail[f"p_low_{eid}"] = p_low
                detail[f"weight_{eid}"] = w

            # 归一化
            if total_weight > 0:
                p_low_fusion /= total_weight

            p_appear_fusion = 1 - p_low_fusion

            # 引擎一致性指标: 6个引擎P_low的标准差
            p_low_values = [detail[f"p_low_{eid}"] for eid in self.engines]
            mean_p_low = sum(p_low_values) / len(p_low_values)
            variance = sum((v - mean_p_low) ** 2 for v in p_low_values) / len(p_low_values)
            consistency = 1 - min(variance * 10, 1.0)  # 方差越小 → 一致性越高

            fusion[n] = {
                **detail,
                "p_low_fusion": round(p_low_fusion, 4),
                "p_appear_fusion": round(p_appear_fusion, 4),
                "engine_consistency": round(consistency, 4),
                "p_low_std": round(variance ** 0.5, 4) if variance > 0 else 0,
            }

        return fusion

    def get_avoid_ranking(self, records: List[Dict] = None) -> List[Tuple[int, float]]:
        """
        🔴 避开模式排名
        按融合P_low从高到低 → P_low越高 = 越不可能出现 → 排越前
        """
        fusion = self.compute_fusion(records)
        ranking = [(n, fusion[n]["p_low_fusion"]) for n in self.pool]
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def get_rebound_ranking(self, records: List[Dict] = None) -> List[Tuple[int, float]]:
        """
        🟢 回补模式排名
        融合P_low + 冷号回补加分
        加分 = 当前间隔期数 × rebound_bonus_per_draw
        """
        from data.processor import DataProcessor
        processor = DataProcessor(self.game_key)

        if records is None:
            records = processor.fetcher.get_all_draws()

        fusion = self.compute_fusion(records)
        current_gaps = processor.compute_current_gap(records)

        rebound_cfg = STRATEGY_CONFIG["rebound"]
        bonus_per_draw = rebound_cfg["rebound_bonus_per_draw"]
        recent_window = rebound_cfg["recent_window"]

        # 计算近期出现次数
        recent_records = processor.fetcher.get_recent_draws(recent_window)
        recent_freq = processor.build_frequency_table(recent_records)

        ranking = []
        for n in self.pool:
            p_low_base = fusion[n]["p_low_fusion"]
            gap = current_gaps.get(n, 0)
            recent_count = recent_freq.get(n, 0)

            # 回补加分: 间隔越长加分越多，近期没出加分更多
            gap_bonus = gap * bonus_per_draw
            cold_bonus = 0
            if recent_count == 0:  # 近N期完全未出现
                cold_bonus = recent_window * bonus_per_draw * 0.5

            p_low_rebound = p_low_base + gap_bonus + cold_bonus
            ranking.append((n, round(p_low_rebound, 4), {
                "p_low_base": p_low_base,
                "gap": gap,
                "recent_count": recent_count,
                "gap_bonus": round(gap_bonus, 4),
                "cold_bonus": round(cold_bonus, 4),
                "p_low_rebound": round(p_low_rebound, 4),
            }))

        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def get_top_n_avoid(self, n: int, records: List[Dict] = None) -> List[Tuple[int, float, Dict]]:
        """🔴 避开模式TopN"""
        fusion = self.compute_fusion(records)
        ranking = sorted(self.pool, key=lambda x: fusion[x]["p_low_fusion"], reverse=True)
        top = ranking[:n]
        return [(num, fusion[num]["p_low_fusion"], fusion[num]) for num in top]

    def get_top_n_rebound(self, n: int, records: List[Dict] = None) -> List[Tuple[int, float, Dict]]:
        """🟢 回补模式TopN"""
        ranking = self.get_rebound_ranking(records)
        top = ranking[:n]
        return top

    def get_full_report(self, records: List[Dict] = None) -> Dict:
        """获取完整预测报告数据"""
        fusion = self.compute_fusion(records)

        avoid_top = {}
        for level in TOP_N_LEVELS:
            avoid_top[level] = self.get_top_n_avoid(level, records)

        rebound_top = {}
        for level in TOP_N_LEVELS:
            rebound_top[level] = self.get_top_n_rebound(level, records)

        # 引擎诊断信息
        engine_diagnosis = {}
        for eid, engine in self.engines.items():
            engine_results = engine.compute(records)
            if eid == "markov":
                signals = [engine_results[n]["markov_signal"] for n in self.pool]
                engine_diagnosis[eid] = {
                    "hot_count": sum(1 for s in signals if s == "hot"),
                    "cold_count": sum(1 for s in signals if s == "cold"),
                    "neutral_count": sum(1 for s in signals if s == "neutral"),
                }
            elif eid == "fft":
                positions = [engine_results[n]["cycle_position"] for n in self.pool]
                engine_diagnosis[eid] = {
                    "peak_count": sum(1 for p in positions if p == "peak"),
                    "valley_count": sum(1 for p in positions if p == "valley"),
                    "transition_count": sum(1 for p in positions if p == "transition"),
                }
            elif eid == "joint":
                signals = [engine_results[n]["joint_signal"] for n in self.pool]
                engine_diagnosis[eid] = {
                    "exclusion_dominant": sum(1 for s in signals if s > 0),
                    "co_occurrence_dominant": sum(1 for s in signals if s < 0),
                    "neutral": sum(1 for s in signals if s == 0),
                }
            elif eid == "monte_carlo":
                # 蒙特卡洛: 统计偏差敏感性分布
                sensitivities = [engine_results[n]["bias_sensitivity"] for n in self.pool]
                positive = sum(1 for s in sensitivities if s > 0)
                negative = sum(1 for s in sensitivities if s < 0)
                near_zero = sum(1 for s in sensitivities if abs(s) < 0.001)
                engine_diagnosis[eid] = {
                    "positive_sensitivity": positive,  # 偏差驱动更容易排除
                    "negative_sensitivity": negative,  # 偏差驱动更不容易排除
                    "near_zero": near_zero,
                    "avg_sensitivity": round(sum(sensitivities) / len(sensitivities), 4),
                    "max_sensitivity": round(max(sensitivities), 4),
                    "min_sensitivity": round(min(sensitivities), 4),
                }

        return {
            "game": self.cfg["name"],
            "game_key": self.game_key,
            "fusion_data": fusion,
            "avoid_top": avoid_top,
            "rebound_top": rebound_top,
            "engine_weights": {eid: self.weights.get(eid, 0) for eid in self.engines},
            "engine_diagnosis": engine_diagnosis,
            "theoretical_prob": self.cfg["theoretical_prob"],
            "theoretical_low_prob": self.cfg["theoretical_low_prob"],
        }

    def get_engine_name(self) -> str:
        return "6引擎融合"

    def get_engine_id(self) -> str:
        return "fusion"
