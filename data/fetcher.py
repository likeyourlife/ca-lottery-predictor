"""
数据采集模块 - 从calottery.com等源获取Fantasy 5历史开奖数据
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from config import GAMES, PROJECT_ROOT, DATA_SOURCES


class DataFetcher:
    """Fantasy 5 / Daily 3/4 数据采集器"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = GAMES[game_key]
        self.data_dir = self.cfg["data_dir"]
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_history_csv(self) -> List[Dict]:
        """从CSV加载历史开奖数据"""
        csv_path = self.cfg["history_csv"]
        if not csv_path.exists():
            return []

        records = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
        return records

    def save_history_csv(self, records: List[Dict], mode: str = "w"):
        """保存历史数据到CSV"""
        csv_path = self.cfg["history_csv"]
        fieldnames = self._get_fieldnames()

        with open(csv_path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if mode == "w":
                writer.writeheader()
            writer.writerows(records)

    def save_latest_json(self, records: List[Dict]):
        """保存最近10期数据到JSON"""
        json_path = self.cfg["latest_json"]
        latest = records[-10:] if len(records) >= 10 else records
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(latest, f, ensure_ascii=False, indent=2)

    def append_records(self, new_records: List[Dict]):
        """增量追加新期数据"""
        existing = self.load_history_csv()
        existing_dates = {r["draw_date"] for r in existing}

        # 过滤已存在的日期
        to_append = [r for r in new_records if r["draw_date"] not in existing_dates]
        if to_append:
            # 按日期排序
            to_append.sort(key=lambda r: r["draw_date"])

            if existing:
                # 追加模式
                all_records = existing + to_append
                all_records.sort(key=lambda r: r["draw_date"])
                self.save_history_csv(all_records, mode="w")
            else:
                # 全量写入
                self.save_history_csv(to_append, mode="w")

            self.save_latest_json(existing + to_append)
            print(f"✅ 追加 {len(to_append)} 条新记录")
        else:
            print("ℹ️ 无新数据需要追加")

    def fetch_from_web(self) -> List[Dict]:
        """
        从web源获取数据 (需配合WebFetch工具使用)
        返回标准化的记录列表
        """
        # 此方法在Skill/Agent中通过WebFetch调用
        # 返回空列表，实际数据由Skill层注入
        return []

    def normalize_record(self, date_str: str, numbers: List[int], jackpot: int = 0) -> Dict:
        """标准化单条记录"""
        if self.game_key == "fantasy5":
            return {
                "draw_date": date_str,
                "num1": numbers[0],
                "num2": numbers[1],
                "num3": numbers[2],
                "num4": numbers[3],
                "num5": numbers[4],
                "jackpot_amount": jackpot,
            }
        elif self.game_key in ("daily3", "daily4"):
            record = {"draw_date": date_str}
            for i, n in enumerate(numbers):
                record[f"position{i+1}"] = n
            record["jackpot_amount"] = jackpot
            return record

    def get_last_draw_date(self) -> Optional[str]:
        """获取最新一期日期"""
        records = self.load_history_csv()
        if records:
            return records[-1]["draw_date"]
        return None

    def get_draw_numbers(self, record: Dict) -> List[int]:
        """从记录中提取开奖号码列表"""
        if self.game_key == "fantasy5":
            return [int(record["num1"]), int(record["num2"]),
                    int(record["num3"]), int(record["num4"]),
                    int(record["num5"])]
        elif self.game_key in ("daily3", "daily4"):
            nums = []
            for i in range(self.cfg["draw_count"]):
                nums.append(int(record[f"position{i+1}"]))
            return nums

    def _get_fieldnames(self) -> List[str]:
        """获取CSV字段名"""
        if self.game_key == "fantasy5":
            return ["draw_date", "num1", "num2", "num3", "num4", "num5", "jackpot_amount"]
        elif self.game_key in ("daily3", "daily4"):
            fields = ["draw_date"]
            for i in range(self.cfg["draw_count"]):
                fields.append(f"position{i+1}")
            fields.append("jackpot_amount")
            return fields

    def get_all_draws(self) -> List[Dict]:
        """获取全部历史开奖"""
        return self.load_history_csv()

    def get_recent_draws(self, n: int = 10) -> List[Dict]:
        """获取最近N期"""
        records = self.load_history_csv()
        return records[-n:] if len(records) >= n else records

    def total_draws(self) -> int:
        """总期数"""
        return len(self.load_history_csv())


def fetch_fantasy5_from_text(raw_text: str) -> List[Dict]:
    """
    从WebFetch获取的原始文本解析Fantasy 5数据
    格式: YYYY-MM-DD,num1,num2,num3,num4,num5
    """
    records = []
    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 6:
            try:
                date_str = parts[0].strip()
                numbers = [int(p.strip()) for p in parts[1:6]]
                if len(numbers) == 5 and all(1 <= n <= 39 for n in numbers):
                    records.append({
                        "draw_date": date_str,
                        "num1": numbers[0],
                        "num2": numbers[1],
                        "num3": numbers[2],
                        "num4": numbers[3],
                        "num5": numbers[4],
                        "jackpot_amount": 0,
                    })
            except (ValueError, IndexError):
                continue
    return records


def init_fantasy5_data(force_reload: bool = False):
    """初始化Fantasy 5基础数据(从内置种子数据 + 补充数据 + Puppeteer抓取数据)"""
    fetcher = DataFetcher("fantasy5")
    if fetcher.total_draws() > 0 and not force_reload:
        print(f"ℹ️ 已有 {fetcher.total_draws()} 条历史数据")
        return fetcher

    # 种子数据: 2025-08至2026-06 约277条
    from data.seed_data import SEED_DATA_FANTASY5

    # 补充数据: 2022年8月-12月 + 2023年8月-12月 + 2024年8月-12月
    from data.supplement_data import ALL_SUPPLEMENT_DATA
    
    # 早期月份补充: 2024年7月-12月 + 2023年8月-12月
    try:
        from data.supplement_early_months import SUPPLEMENT_EARLY_DATA
        all_data = SEED_DATA_FANTASY5 + ALL_SUPPLEMENT_DATA + SUPPLEMENT_EARLY_DATA
    except ImportError:
        all_data = SEED_DATA_FANTASY5 + ALL_SUPPLEMENT_DATA
    
    # Puppeteer抓取补充数据: 2022-2025完整数据
    try:
        from data.supplement_scraped import SUPPLEMENT_SCRAPED_DATA
        all_data = all_data + SUPPLEMENT_SCRAPED_DATA
    except ImportError:
        pass

    # 合并所有数据(按日期排序, 去重)
    all_data_merged = all_data

    # 去重(按draw_date)
    seen = set()
    unique_data = []
    for record in all_data_merged:
        if record["draw_date"] not in seen:
            seen.add(record["draw_date"])
            unique_data.append(record)

    # 按日期排序
    unique_data.sort(key=lambda r: r["draw_date"])

    fetcher.save_history_csv(unique_data, mode="w")
    fetcher.save_latest_json(unique_data)
    source_info = f"种子{len(SEED_DATA_FANTASY5)}"
    source_info += f" + 补充{len(ALL_SUPPLEMENT_DATA)}"
    try:
        from data.supplement_early_months import SUPPLEMENT_EARLY_DATA
        source_info += f" + 早期{len(SUPPLEMENT_EARLY_DATA)}"
    except ImportError:
        pass
    try:
        from data.supplement_scraped import SUPPLEMENT_SCRAPED_DATA
        source_info += f" + 抓取{len(SUPPLEMENT_SCRAPED_DATA)}"
    except ImportError:
        pass
    print(f"✅ 初始化 {len(unique_data)} 条Fantasy 5历史数据 ({source_info})")
    return fetcher
