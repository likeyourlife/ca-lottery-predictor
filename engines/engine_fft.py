"""
E5: FFT周期引擎
核心算法: 快速傅里叶变换频谱分析 → 检测号码出现的时间周期性
原理: 每个号码的出现序列(0/1)被视为时域信号, 通过FFT分解为频域分量
      识别主周期 → 判断号码当前处于周期"活跃期"还是"低谷期"
输出: P_low(i) = 1 - 周期预测出现概率
"""

import math
from typing import Dict, List, Tuple

from config import GAMES, get_game_config, get_number_pool
from data.processor import DataProcessor

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class FFTEngine:
    """FFT周期引擎 - 频谱周期性检测"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.processor = DataProcessor(game_key)
        self.pool = get_number_pool(game_key)

        self.m = self.cfg["draw_count"]   # 5
        self.K = len(self.pool)            # 39
        self.theoretical_prob = self.m / self.K
        self.theoretical_low_prob = 1 - self.theoretical_prob

    def compute(self, records: List[Dict] = None) -> Dict[int, Dict]:
        """
        计算FFT周期预测

        流程:
        1. 对每个号码的出现序列(0/1)做FFT
        2. 找主频分量(排除直流分量和极低频)
        3. 根据主频重构预测信号
        4. 判断当前相位位置 → 预测下一期出现概率

        返回: {
            number: {
                "dominant_period": float,     # 主周期(期数)
                "dominant_freq_idx": int,     # 主频索引
                "dominant_amplitude": float,  # 主频振幅
                "spectral_energy": float,     # 频谱总能量(排除直流)
                "cycle_phase": float,         # 当前周期相位 (0~1)
                "cycle_position": str,        # "peak"/"valley"/"transition"
                "p_appear": float,            # FFT预测出现概率
                "p_low": float,               # FFT预测不出现概率
                "periodicity_strength": float, # 周期性强度指标
            }
        }
        """
        if records is None:
            records = self.processor.fetcher.get_all_draws()

        if not records or len(records) < 30:
            return self._default_results()

        if not HAS_NUMPY:
            return self._compute_dft_fallback(records)

        # 构建出现序列
        presence = self.processor.build_presence_series(records)
        N = len(records)

        results = {}
        for n in self.pool:
            series = np.array(presence[n], dtype=np.float64)

            # ── FFT变换 ──
            fft_result = np.fft.rfft(series)
            frequencies = np.fft.rfftfreq(N, d=1.0)  # 频率(每期)
            amplitudes = np.abs(fft_result)

            # ── 找主频 ──
            # 排除直流分量(idx=0)和极低频(idx=1, 频率<1/N)
            # 关注周期在3~50期之间的分量
            valid_mask = frequencies > 1.0 / N  # 排除直流和极低频

            # 限制周期范围: 3期~N/2期
            min_freq = 1.0 / 50  # 最长周期50期
            max_freq = 1.0 / 3   # 最短周期3期
            period_mask = (frequencies >= min_freq) & (frequencies <= max_freq)

            combined_mask = valid_mask & period_mask
            valid_amplitudes = amplitudes.copy()
            valid_amplitudes[~combined_mask] = 0

            # 主频索引(振幅最大)
            dominant_idx = np.argmax(valid_amplitudes)
            if valid_amplitudes[dominant_idx] == 0:
                # 没有找到有效主频 → 无周期性
                results[n] = self._no_periodicity_result()
                continue

            dominant_freq = frequencies[dominant_idx]
            dominant_amplitude = amplitudes[dominant_idx]
            dominant_period = 1.0 / dominant_freq if dominant_freq > 0 else N

            # ── 频谱能量(排除直流) ──
            spectral_energy = np.sum(amplitudes[1:] ** 2)  # 排除直流分量
            total_energy = np.sum(series ** 2)
            periodicity_strength = spectral_energy / total_energy if total_energy > 0 else 0

            # ── 当前周期相位 ──
            # 使用主频分量重构当前时刻的相位
            phase = fft_result[dominant_idx]
            current_phase = math.atan2(phase.imag, phase.real)
            cycle_phase = (current_phase / (2 * math.pi)) % 1.0  # 归一化到0~1

            # ── 判断周期位置 ──
            # phase接近0 → 正弦波上升段(活跃期前)
            # phase接近0.25 → 峰值(活跃期)
            # phase接近0.5 → 下降段(活跃期后)
            # phase接近0.75 → 谷值(低谷期)
            if 0.0 <= cycle_phase < 0.25 or 0.9 <= cycle_phase <= 1.0:
                cycle_position = "peak"      # 接近峰值/上升 → 高出现概率
            elif 0.25 <= cycle_phase < 0.5:
                cycle_position = "transition"  # 过渡区
            elif 0.5 <= cycle_phase < 0.75:
                cycle_position = "valley"    # 接近谷值 → 低出现概率
            else:
                cycle_position = "transition"

            # ── P_low计算 ──
            # 基于周期位置和周期强度
            # 周期强度越高 → 周期性越明显 → P_low偏离理论值越大
            # valley位置 → P_low偏高(不容易出现)
            # peak位置 → P_low偏低(容易出现)

            position_factor = {
                "peak": -0.03,       # 峰值: P_low下调3%
                "transition": 0,     # 过渡: P_low不变
                "valley": 0.03,      # 谷值: P_low上调3%
            }

            # 周期性越强, 位置调整越显著
            strength_scale = min(periodicity_strength * 2, 1.0)  # 缩放到[0,1]
            adjustment = position_factor.get(cycle_position, 0) * strength_scale

            p_low = self.theoretical_low_prob + adjustment
            p_low = max(0.80, min(0.95, p_low))  # 合理范围
            p_appear = 1 - p_low

            results[n] = {
                "dominant_period": round(dominant_period, 2),
                "dominant_freq_idx": dominant_idx,
                "dominant_amplitude": round(dominant_amplitude, 4),
                "spectral_energy": round(spectral_energy, 4),
                "cycle_phase": round(cycle_phase, 4),
                "cycle_position": cycle_position,
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "periodicity_strength": round(periodicity_strength, 4),
            }

        return results

    def _compute_dft_fallback(self, records: List[Dict]) -> Dict[int, Dict]:
        """
        无numpy时的简化DFT实现(仅提取最显著的几个频率分量)
        """
        presence = self.processor.build_presence_series(records)
        N = len(records)

        results = {}
        for n in self.pool:
            series = presence[n]

            # 简化: 只计算几个固定周期的平均振幅
            # 周期 = 5, 7, 10, 14, 20, 30
            check_periods = [5, 7, 10, 14, 20, 30]

            best_period = 0
            best_amplitude = 0
            best_phase = 0

            for period in check_periods:
                # 计算该周期的振幅
                cos_sum = 0
                sin_sum = 0
                for t in range(N):
                    angle = 2 * math.pi * t / period
                    cos_sum += series[t] * math.cos(angle)
                    sin_sum += series[t] * math.sin(angle)

                amplitude = math.sqrt(cos_sum ** 2 + sin_sum ** 2) / N
                phase = math.atan2(sin_sum, cos_sum)

                if amplitude > best_amplitude:
                    best_amplitude = amplitude
                    best_period = period
                    best_phase = phase

            # 当前相位位置
            cycle_phase = (best_phase / (2 * math.pi)) % 1.0

            if 0.0 <= cycle_phase < 0.25 or 0.9 <= cycle_phase <= 1.0:
                cycle_position = "peak"
            elif 0.25 <= cycle_phase < 0.5:
                cycle_position = "transition"
            elif 0.5 <= cycle_phase < 0.75:
                cycle_position = "valley"
            else:
                cycle_position = "transition"

            # 周期性强度(简化)
            total_variance = sum((x - self.theoretical_prob) ** 2 for x in series) / N
            periodicity_strength = min(best_amplitude / math.sqrt(total_variance) if total_variance > 0 else 0, 1.0)

            position_factor = {"peak": -0.03, "transition": 0, "valley": 0.03}
            adjustment = position_factor.get(cycle_position, 0) * periodicity_strength

            p_low = self.theoretical_low_prob + adjustment
            p_low = max(0.80, min(0.95, p_low))
            p_appear = 1 - p_low

            results[n] = {
                "dominant_period": best_period,
                "dominant_freq_idx": 0,
                "dominant_amplitude": round(best_amplitude, 4),
                "spectral_energy": 0,
                "cycle_phase": round(cycle_phase, 4),
                "cycle_position": cycle_position,
                "p_appear": round(p_appear, 4),
                "p_low": round(p_low, 4),
                "periodicity_strength": round(periodicity_strength, 4),
            }

        return results

    def _no_periodicity_result(self) -> Dict:
        """无显著周期性时的结果"""
        return {
            "dominant_period": 0,
            "dominant_freq_idx": 0,
            "dominant_amplitude": 0,
            "spectral_energy": 0,
            "cycle_phase": 0.5,
            "cycle_position": "transition",
            "p_appear": round(self.theoretical_prob, 4),
            "p_low": round(self.theoretical_low_prob, 4),
            "periodicity_strength": 0,
        }

    def _default_results(self) -> Dict[int, Dict]:
        """数据不足时返回理论基线"""
        results = {}
        for n in self.pool:
            results[n] = self._no_periodicity_result()
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
        return "E5 FFT周期"

    def get_engine_id(self) -> str:
        return "fft"
