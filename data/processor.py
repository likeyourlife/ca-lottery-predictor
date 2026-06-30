"""
数据标准化与处理模块
"""

import json
from typing import List, Dict, Tuple
from pathlib import Path

from config import GAMES, CACHE_DIR
from data.fetcher import DataFetcher


class DataProcessor:
    """数据标准化与特征提取"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = GAMES[game_key]
        self.fetcher = DataFetcher(game_key)

    def get_number_pool(self) -> List[int]:
        """获取号码池"""
        lo, hi = self.cfg["number_range"]
        return list(range(lo, hi + 1))

    def extract_numbers_from_record(self, record: Dict) -> List[int]:
        """从单条记录中提取开奖号码"""
        if self.game_key == "fantasy5":
            return [int(record["num1"]), int(record["num2"]),
                    int(record["num3"]), int(record["num4"]),
                    int(record["num5"])]
        elif self.game_key in ("daily3", "daily4"):
            nums = []
            for i in range(self.cfg["draw_count"]):
                nums.append(int(record[f"position{i+1}"]))
            return nums
        return []

    def build_frequency_table(self, records: List[Dict]) -> Dict[int, int]:
        """
        构建频次表: 每个号码出现次数
        """
        pool = self.get_number_pool()
        freq = {n: 0 for n in pool}

        for record in records:
            numbers = self.extract_numbers_from_record(record)
            for n in numbers:
                if n in freq:
                    freq[n] += 1

        return freq

    def build_presence_series(self, records: List[Dict]) -> Dict[int, List[int]]:
        """
        构建出现序列: 每个号码每期是否出现(1/0)
        按时间从旧到新排列
        """
        pool = self.get_number_pool()
        series = {n: [] for n in pool}

        # 按日期排序(从旧到新)
        sorted_records = sorted(records, key=lambda r: r["draw_date"])

        for record in sorted_records:
            numbers = self.extract_numbers_from_record(record)
            for n in pool:
                series[n].append(1 if n in numbers else 0)

        return series

    def build_gap_series(self, records: List[Dict]) -> Dict[int, List[int]]:
        """
        构建间隔序列: 每个号码两次出现之间的期数间隔
        """
        presence = self.build_presence_series(records)
        gaps = {}

        for n in self.get_number_pool():
            positions = [i for i, v in enumerate(presence[n]) if v == 1]
            if len(positions) <= 1:
                gaps[n] = []
                continue

            gap_list = []
            for j in range(1, len(positions)):
                gap_list.append(positions[j] - positions[j-1])
            gaps[n] = gap_list

        return gaps

    def compute_current_gap(self, records: List[Dict]) -> Dict[int, int]:
        """
        计算当前间隔: 每个号码距上次出现的期数
        """
        presence = self.build_presence_series(records)
        current_gaps = {}

        for n in self.get_number_pool():
            series = presence[n]
            # 从最近一期往回找
            gap = 0
            for i in range(len(series) - 1, -1, -1):
                if series[i] == 1:
                    gap = len(series) - 1 - i
                    break
            if gap == 0 and series[-1] == 0:
                # 全部历史都没出现过(不应该发生)
                gap = len(series)
            current_gaps[n] = gap

        return current_gaps

    def get_recent_draws_numbers(self, n: int = 10) -> List[List[int]]:
        """获取最近N期的开奖号码列表"""
        records = self.fetcher.get_recent_draws(n)
        return [self.extract_numbers_from_record(r) for r in records]

    def compute_stats_summary(self) -> Dict:
        """
        计算统计摘要
        """
        records = self.fetcher.get_all_draws()
        if not records:
            return {}

        freq = self.build_frequency_table(records)
        total_draws = len(records)
        m = self.cfg["draw_count"]  # 每期开出数
        K = len(self.get_number_pool())  # 号码池大小

        # 理论期望频次
        expected_freq = total_draws * (m / K)

        # Z-score偏差
        stats = {}
        for n in self.get_number_pool():
            observed = freq[n]
            sigma = (total_draws * (m / K) * (1 - m / K)) ** 0.5
            z_score = (observed - expected_freq) / sigma if sigma > 0 else 0
            stats[n] = {
                "observed_freq": observed,
                "expected_freq": expected_freq,
                "z_score": z_score,
                "deviation_pct": (observed - expected_freq) / expected_freq * 100 if expected_freq > 0 else 0,
            }

        return {
            "total_draws": total_draws,
            "number_pool_size": K,
            "draw_count_per_draw": m,
            "theoretical_prob": m / K,
            "freq_table": freq,
            "number_stats": stats,
        }

    def initialize_data(self):
        """初始化数据(加载种子数据)"""
        from .fetcher import init_fantasy5_data
        return init_fantasy5_data()
