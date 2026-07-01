"""
全局配置 - 游戏参数、引擎权重、数据路径
"""

import os
from pathlib import Path

# ── 项目根目录 ──
PROJECT_ROOT = Path(__file__).parent

# ── 游戏定义 ──
GAMES = {
    "fantasy5": {
        "name": "Fantasy 5",
        "number_range": (1, 39),       # 号码池 1-39
        "draw_count": 5,               # 每期开出5个号
        "total_combinations": 575757,  # C(39,5)
        "theoretical_prob": 5 / 39,    # 单号理论出现概率 ≈ 0.1282
        "theoretical_low_prob": 34 / 39,  # 单号理论不出现概率 ≈ 0.8718
        "draw_frequency": "daily",
        "priority": "P0",
        "data_dir": PROJECT_ROOT / "data" / "fantasy5",
        "history_csv": PROJECT_ROOT / "data" / "fantasy5" / "history.csv",
        "latest_json": PROJECT_ROOT / "data" / "fantasy5" / "latest.json",
    },
    "daily3": {
        "name": "Daily 3",
        "number_range": (0, 9),
        "draw_count": 3,               # 3位数字, 可重复
        "total_combinations": 1000,
        "theoretical_prob": 1 / 10,
        "theoretical_low_prob": 9 / 10,
        "draw_frequency": "daily",
        "priority": "P1",
        "data_dir": PROJECT_ROOT / "data" / "daily3",
        "history_csv": PROJECT_ROOT / "data" / "daily3" / "history.csv",
        "latest_json": PROJECT_ROOT / "data" / "daily3" / "latest.json",
    },
    "daily4": {
        "name": "Daily 4",
        "number_range": (0, 9),
        "draw_count": 4,
        "total_combinations": 10000,
        "theoretical_prob": 1 / 10,
        "theoretical_low_prob": 9 / 10,
        "draw_frequency": "daily",
        "priority": "P1",
        "data_dir": PROJECT_ROOT / "data" / "daily4",
        "history_csv": PROJECT_ROOT / "data" / "daily4" / "history.csv",
        "latest_json": PROJECT_ROOT / "data" / "daily4" / "latest.json",
    },
}

# ── 默认游戏 ──
DEFAULT_GAME = "fantasy5"

# ── 引擎权重 (回测驱动调优 v3: 随机搜索100组+平衡搜索+多窗口验证) ──
# 优化结果: avg Top10 margin=+0.87% > v2的+0.02%
# 关键发现: 马尔可夫权重应提升至60%, 贝叶斯降至10%, 连号联合降至26%
# 稳定性: 3/4窗口跑赢基线(W=100:-2.37%, W=200:+0.13%, W=300:+4.30%, W=500:+1.43%)
# 最佳验证窗口: W=300 (+4.30% Top10命中率)
ENGINE_WEIGHTS = {
    "fantasy5": {
        "freq": 0.02,
        "bayesian": 0.10,
        "markov": 0.60,
        "joint": 0.26,
        "fft": 0.02,
        "monte_carlo": 0.00,
    },
}

# ── 贝叶斯引擎参数 ──
BAYESIAN_CONFIG = {
    "fantasy5": {
        "prior_weight": 50,            # 先验强度
        # alpha0 = theoretical_prob * prior_weight ≈ 6.41
        # beta0 = theoretical_low_prob * prior_weight ≈ 43.59
    },
}

# ── 策略模式参数 ──
STRATEGY_CONFIG = {
    "avoid": {
        "name": "避开模式",
        "emoji": "🔴",
        "description": "直接取融合概率最高的TopN → 最不可能出的号",
    },
    "rebound": {
        "name": "回补模式",
        "emoji": "🟢",
        "description": "冷号可能即将回补 → 近期未出现的号加分",
        "rebound_bonus_per_draw": 0.002,  # 每期未出加分
        "recent_window": 10,              # 近N期判断冷号
    },
}

# ── TopN 层级 ──
TOP_N_LEVELS = [2, 4, 10]

# ── 回测参数 ──
BACKTEST_CONFIG = {
    "window": 200,                # 近N期回测(v3: 从100→200, 优化权重在此窗口表现更好)
    "avoid_target_top10": 0.72,   # 避开命中率目标
    "rebound_target_top4": 0.50,  # 回补命中率目标(至少1个)
    "engine_consistency_min": 0.60,
}

# ── 数据源 ──
DATA_SOURCES = {
    "fantasy5_history": "https://www.calottery.com/site/archive",
    "fantasy5_api": "https://www.calottery.com/api/v1.5/games/fantasy5/draws",
    "daily3_api": "https://www.calottery.com/api/v1.5/games/daily3/draws",
    "daily4_api": "https://www.calottery.com/api/v1.5/games/daily4/draws",
}

# ── 缓存目录 ──
CACHE_DIR = PROJECT_ROOT / "data" / "features"
MODELS_DIR = PROJECT_ROOT / "models"

# ── 置信度标注 ──
CONFIDENCE_LABEL = "B (统计级, 非因果级)"

# ── 免责声明 ──
DISCLAIMER = "本软件不声称能预测彩票中奖号码。彩票开奖本质为随机过程，模型输出的概率排序仅为统计参考，不构成投注建议。"


def get_game_config(game_key: str = None) -> dict:
    """获取游戏配置"""
    if game_key is None:
        game_key = DEFAULT_GAME
    return GAMES[game_key]


def get_number_pool(game_key: str = None) -> list:
    """获取号码池"""
    cfg = get_game_config(game_key)
    lo, hi = cfg["number_range"]
    return list(range(lo, hi + 1))
