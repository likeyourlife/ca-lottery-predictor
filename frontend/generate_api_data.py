#!/usr/bin/env python3
"""
API数据生成器 - 为前端页面生成所有需要的JSON数据
每次运行预测后调用，更新前端数据文件
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GAME, ENGINE_WEIGHTS, TOP_N_LEVELS, CONFIDENCE_LABEL, DISCLAIMER
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from engines.engine_fusion import EngineFusion
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
from output.topn_selector import TopNSelector
from backtest.backtest_runner import BacktestRunner


def get_numbers_from_draw(draw):
    """从draw记录中提取号码列表"""
    nums = []
    for key in ["num1", "num2", "num3", "num4", "num5"]:
        if key in draw:
            nums.append(int(draw[key]))
    return nums

def get_date_from_draw(draw):
    """从draw记录中提取日期"""
    return draw.get("draw_date", draw.get("date", ""))


def generate_frontend_data(game_key: str = DEFAULT_GAME):
    """生成前端所需的全部JSON数据"""
    
    FRONTEND_DIR = PROJECT_ROOT / "frontend"
    
    # 初始化数据
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    
    # 生成预测结果
    avoid = AvoidMode(game_key)
    avoid_result = avoid.predict(records)
    
    rebound = ReboundMode(game_key)
    rebound_result = rebound.predict(records)
    
    # ── 1. 当日预测结果 ──
    prediction_data = {
        "generated_at": datetime.now().isoformat(),
        "game": "Fantasy 5",
        "number_range": "1-39",
        "draw_count": 5,
        "data_count": len(records),
        "last_draw_date": get_date_from_draw(records[-1]) if records else "",
        "confidence": CONFIDENCE_LABEL,
        "disclaimer": DISCLAIMER,
        "weights": ENGINE_WEIGHTS.get(game_key, {}),
        "avoid": {},
        "rebound": {},
    }
    
    for level in TOP_N_LEVELS:
        top_key = f"top{level}"
        prediction_data["avoid"][top_key] = [
            {"number": int(t[0]), "p_low": round(t[1], 4)}
            for t in avoid_result.get(top_key, [])
        ]
        prediction_data["rebound"][top_key] = [
            {
                "number": int(t[0]), 
                "p_low": round(t[1], 4), 
                "gap": t[2].get("gap", 0) if isinstance(t[2], dict) else 0,
                "gap_bonus": round(t[2].get("gap_bonus", 0), 4) if isinstance(t[2], dict) else 0,
            }
            for t in rebound_result.get(top_key, [])
        ]
    
    pred_path = FRONTEND_DIR / "prediction.json"
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(prediction_data, f, ensure_ascii=False, indent=2)
    
    # ── 2. 最近10天开奖+预测对比 ──
    recent_draws = []
    # 取最近10期开奖数据
    last_10 = records[-10:] if len(records) >= 10 else records
    
    for draw in last_10:
        draw_numbers = get_numbers_from_draw(draw)
        # 计算该期的避开Top10号码(用历史数据的前N期预测)
        draw_info = {
            "date": get_date_from_draw(draw),
            "winning_numbers": draw_numbers,
            "top2_avoid": [],
            "top4_avoid": [],
            "top10_avoid": [],
            "top2_hit": False,
            "top4_hit": False,
            "top10_hit": False,
        }
        recent_draws.append(draw_info)
    
    # 对最近10期做回测对比
    runner = BacktestRunner(game_key)
    if len(records) >= 110:
        bt_result = runner.run_backtest(window=10)
        period_results = bt_result.get("period_results", [])
        
        for i, pr in enumerate(period_results[:10]):
            if i < len(recent_draws):
                actual_nums = pr["actual_numbers"]
                for level in TOP_N_LEVELS:
                    predicted_nums = pr["avoid_predicted"][level]
                    recent_draws[i][f"top{level}_avoid"] = predicted_nums
                    recent_draws[i][f"top{level}_hit"] = any(
                        n in actual_nums for n in predicted_nums
                    )
    
    recent_path = FRONTEND_DIR / "recent_draws.json"
    with open(recent_path, "w", encoding="utf-8") as f:
        json.dump(recent_draws, f, ensure_ascii=False, indent=2)
    
    # ── 3. 历史准确率(近1年月为单位) ──
    monthly_accuracy = []
    # 简化：用最近12个月的回测数据
    for window in [30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 350, 400]:
        if len(records) >= window + 10:
            bt = runner.run_backtest(window=window)
            stats = bt["avoid_stats"]
            month_data = {
                "window": window,
                "top2": {
                    "hit_rate": round(stats[2]["hit_rate"], 4),
                    "baseline": round(stats[2]["random_baseline"], 4),
                    "margin": round(stats[2]["margin"], 4),
                },
                "top4": {
                    "hit_rate": round(stats[4]["hit_rate"], 4),
                    "baseline": round(stats[4]["random_baseline"], 4),
                    "margin": round(stats[4]["margin"], 4),
                },
                "top10": {
                    "hit_rate": round(stats[10]["hit_rate"], 4),
                    "baseline": round(stats[10]["random_baseline"], 4),
                    "margin": round(stats[10]["margin"], 4),
                },
            }
            monthly_accuracy.append(month_data)
    
    monthly_path = FRONTEND_DIR / "monthly_accuracy.json"
    with open(monthly_path, "w", encoding="utf-8") as f:
        json.dump(monthly_accuracy, f, ensure_ascii=False, indent=2)
    
    # ── 4. 连续不中奖期数 ──
    consecutive_data = {}
    pool = list(range(1, 40))
    
    # 计算每个号码距离上次出现的期数
    for num in pool:
        last_appear = 0
        for i, draw in enumerate(records):
            if num in get_numbers_from_draw(draw):
                last_appear = i
        consecutive_data[num] = len(records) - 1 - last_appear
    
    consec_path = FRONTEND_DIR / "consecutive_absence.json"
    with open(consec_path, "w", encoding="utf-8") as f:
        json.dump(consecutive_data, f, ensure_ascii=False, indent=2)
    
    # ── 5. 每日准确率(近30天) ──
    daily_accuracy = []
    if len(records) >= 110:
        bt_full = runner.run_backtest(window=100)
        period_results = bt_full.get("period_results", [])
        
        for i, pr in enumerate(period_results[:30]):
            day_data = {
                "date": get_date_from_draw(records[-(i+1)]) if i < len(records) else "",
                "top2_hit": any(n in pr["actual_numbers"] for n in pr["avoid_predicted"][2]),
                "top4_hit": any(n in pr["actual_numbers"] for n in pr["avoid_predicted"][4]),
                "top10_hit": any(n in pr["actual_numbers"] for n in pr["avoid_predicted"][10]),
            }
            daily_accuracy.append(day_data)
    
    daily_path = FRONTEND_DIR / "daily_accuracy.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(daily_accuracy, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 前端数据已生成:")
    print(f"  prediction.json: {pred_path}")
    print(f"  recent_draws.json: {recent_path}")
    print(f"  monthly_accuracy.json: {monthly_path}")
    print(f"  consecutive_absence.json: {consec_path}")
    print(f"  daily_accuracy.json: {daily_path}")


if __name__ == "__main__":
    generate_frontend_data()
