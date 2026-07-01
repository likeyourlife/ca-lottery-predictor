#!/usr/bin/env python3
"""
API数据生成器 - 为前端页面生成所有需要的JSON数据
每次运行预测后调用，更新前端数据文件
v2: 修复键名对齐问题，正确映射回测结果到最近开奖数据
"""

import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GAME, ENGINE_WEIGHTS, TOP_N_LEVELS, CONFIDENCE_LABEL, DISCLAIMER
from data.fetcher import DataFetcher, init_fantasy5_data
from data.processor import DataProcessor
from engines.engine_fusion import EngineFusion
from strategy.avoid_mode import AvoidMode
from strategy.rebound_mode import ReboundMode
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
    processor = DataProcessor(game_key)
    
    # 初始化数据
    fetcher = init_fantasy5_data()
    records = fetcher.get_all_draws()
    total = len(records)
    
    # 生成预测结果(用全部历史数据)
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
        "data_count": total,
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
    
    # ── 2. 最近10期开奖+回测预测对比 ──
    # 策略: 用回测backtest window=10的结果，直接取per_period_details
    # per_period_details的时间范围就是最后10+10期的验证结果
    recent_draws = []
    
    runner = BacktestRunner(game_key)
    if total >= 60:  # window=10 需要 window+50=60
        bt_result = runner.run_backtest(window=10)
        details = bt_result.get("per_period_details", [])
        
        for pr in details[:10]:
            draw_info = {
                "date": pr.get("draw_date", ""),
                "winning_numbers": pr.get("actual_numbers", []),
                "top2_avoid": pr.get("avoid_top2", []),
                "top4_avoid": pr.get("avoid_top4", []),
                "top10_avoid": pr.get("avoid_top10", []),
                "top2_hit": pr.get("avoid_hit_top2", 0) >= 1,
                "top4_hit": pr.get("avoid_hit_top4", 0) >= 1,
                "top10_hit": pr.get("avoid_hit_top10", 0) >= 1,
                "top2_hit_count": pr.get("avoid_hit_top2", 0),
                "top4_hit_count": pr.get("avoid_hit_top4", 0),
                "top10_hit_count": pr.get("avoid_hit_top10", 0),
            }
            recent_draws.append(draw_info)
    else:
        # 数据不足回测，直接展示开奖号
        last_10 = records[-10:] if total >= 10 else records
        for draw in last_10:
            recent_draws.append({
                "date": get_date_from_draw(draw),
                "winning_numbers": get_numbers_from_draw(draw),
                "top2_avoid": [], "top4_avoid": [], "top10_avoid": [],
                "top2_hit": False, "top4_hit": False, "top10_hit": False,
                "top2_hit_count": 0, "top4_hit_count": 0, "top10_hit_count": 0,
            })
    
    recent_path = FRONTEND_DIR / "recent_draws.json"
    with open(recent_path, "w", encoding="utf-8") as f:
        json.dump(recent_draws, f, ensure_ascii=False, indent=2)
    
    # ── 3. 历史准确率(多窗口回测) ──
    monthly_accuracy = []
    for window in [30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 350, 400]:
        if total >= window + 50:
            bt = runner.run_backtest(window=window)
            stats = bt.get("avoid_stats", {})
            if stats:
                month_data = {
                    "window": window,
                    "top2": {
                        "hit_rate": stats.get(2, {}).get("hit_rate", 0),
                        "baseline": stats.get(2, {}).get("random_baseline", 0),
                        "margin": stats.get(2, {}).get("margin", 0),
                    },
                    "top4": {
                        "hit_rate": stats.get(4, {}).get("hit_rate", 0),
                        "baseline": stats.get(4, {}).get("random_baseline", 0),
                        "margin": stats.get(4, {}).get("margin", 0),
                    },
                    "top10": {
                        "hit_rate": stats.get(10, {}).get("hit_rate", 0),
                        "baseline": stats.get(10, {}).get("random_baseline", 0),
                        "margin": stats.get(10, {}).get("margin", 0),
                    },
                }
                monthly_accuracy.append(month_data)
    
    monthly_path = FRONTEND_DIR / "monthly_accuracy.json"
    with open(monthly_path, "w", encoding="utf-8") as f:
        json.dump(monthly_accuracy, f, ensure_ascii=False, indent=2)
    
    # ── 4. 连续不中奖期数 ──
    consecutive_data = {}
    pool = list(range(1, 40))
    
    # 计算每个号码距离上次出现的期数(从最新期倒查)
    for num in pool:
        gap = 0
        for i in range(total - 1, -1, -1):
            draw_nums = get_numbers_from_draw(records[i])
            if num in draw_nums:
                gap = total - 1 - i
                break
        consecutive_data[str(num)] = gap
    
    consec_path = FRONTEND_DIR / "consecutive_absence.json"
    with open(consec_path, "w", encoding="utf-8") as f:
        json.dump(consecutive_data, f, ensure_ascii=False, indent=2)
    
    # ── 5. 每日准确率(近30期) ──
    daily_accuracy = []
    if total >= 150:  # window=100 需要 window+50=150
        bt_full = runner.run_backtest(window=100)
        details = bt_full.get("per_period_details", [])
        
        # 取最后30期的详情(倒序, 最近的在前)
        last_30 = details[-30:] if len(details) >= 30 else details
        
        for pr in reversed(last_30):  # 最近的期次排在前面
            day_data = {
                "date": pr.get("draw_date", ""),
                "top2_hit": pr.get("avoid_hit_top2", 0) >= 1,
                "top4_hit": pr.get("avoid_hit_top4", 0) >= 1,
                "top10_hit": pr.get("avoid_hit_top10", 0) >= 1,
                "top2_count": pr.get("avoid_hit_top2", 0),
                "top4_count": pr.get("avoid_hit_top4", 0),
                "top10_count": pr.get("avoid_hit_top10", 0),
            }
            daily_accuracy.append(day_data)
    
    daily_path = FRONTEND_DIR / "daily_accuracy.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(daily_accuracy, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 前端数据已生成 (v2):")
    print(f"  prediction.json → {pred_path}")
    print(f"  recent_draws.json → {recent_path} ({len(recent_draws)}期)")
    print(f"  monthly_accuracy.json → {monthly_path} ({len(monthly_accuracy)}窗口)")
    print(f"  consecutive_absence.json → {consec_path}")
    print(f"  daily_accuracy.json → {daily_path} ({len(daily_accuracy)}期)")


if __name__ == "__main__":
    generate_frontend_data()
