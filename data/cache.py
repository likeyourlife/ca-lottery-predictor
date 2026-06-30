"""
特征缓存管理模块
"""

import pickle
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from config import CACHE_DIR


class FeatureCache:
    """特征缓存管理器 - 避免重复计算"""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return CACHE_DIR / f"{key}.pkl"

    def save(self, key: str, data: Any):
        """保存缓存"""
        path = self._get_path(key)
        with open(path, "wb") as f:
            pickle.dump({
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }, f)

    def load(self, key: str) -> Optional[Any]:
        """加载缓存"""
        path = self._get_path(key)
        if not path.exists():
            return None

        with open(path, "rb") as f:
            cache = pickle.load(f)
        return cache["data"]

    def is_cached(self, key: str) -> bool:
        """检查缓存是否存在"""
        return self._get_path(key).exists()

    def get_timestamp(self, key: str) -> Optional[str]:
        """获取缓存时间戳"""
        path = self._get_path(key)
        if not path.exists():
            return None

        with open(path, "rb") as f:
            cache = pickle.load(f)
        return cache.get("timestamp")

    def clear(self, key: str = None):
        """清除缓存"""
        if key:
            path = self._get_path(key)
            if path.exists():
                path.unlink()
        else:
            for p in CACHE_DIR.glob("*.pkl"):
                p.unlink()

    def list_keys(self) -> list:
        """列出所有缓存键"""
        return [p.stem for p in CACHE_DIR.glob("*.pkl")]
