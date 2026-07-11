"""
RAG 分层缓存
L1: 内存缓存（查询 hash -> 结果）
L2: Redis 缓存（持久化）
减少重复检索的计算开销
"""
import hashlib
import json
import time
from typing import Optional, Any

from app.config import config


class RAGCache:
    """
    分层缓存
    L1: 内存 dict（热数据，极速）
    L2: Redis（持久化，跨会话共享）
    """

    def __init__(self, max_size: int = 500, ttl: int = 3600):
        self._l1: dict[str, dict] = {}  # key -> {"data": ..., "expire": ...}
        self._max_size = max_size
        self._ttl = ttl
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.Redis(
                host=config.redis.host,
                port=config.redis.port,
                db=config.redis.db,
                password=config.redis.password or None,
                decode_responses=True,
            )
            self._redis.ping()
        except Exception:
            print("[RAGCache] Redis 不可用，仅使用内存缓存")
            self._redis = None

    def _make_key(self, query: str) -> str:
        return f"rag_cache:{hashlib.md5(query.encode()).hexdigest()}"

    def get(self, query: str) -> Optional[list[dict]]:
        """获取缓存"""
        key = self._make_key(query)

        # L1 内存
        if key in self._l1:
            entry = self._l1[key]
            if entry["expire"] > time.time():
                return entry["data"]
            del self._l1[key]

        # L2 Redis
        if self._redis:
            raw = self._redis.get(key)
            if raw:
                data = json.loads(raw)
                # 回填 L1
                self._set_l1(key, data)
                return data

        return None

    def set(self, query: str, data: list[dict]):
        """设置缓存"""
        key = self._make_key(query)
        self._set_l1(key, data)

        if self._redis:
            try:
                self._redis.setex(key, self._ttl, json.dumps(data, ensure_ascii=False, default=str))
            except Exception as e:
                print(f"[RAGCache] Redis 写入失败: {e}")

    def _set_l1(self, key: str, data: Any):
        """写入 L1"""
        if len(self._l1) >= self._max_size:
            # 简单 LRU：删除最早过期的一项
            oldest = min(self._l1.items(), key=lambda x: x[1]["expire"])
            del self._l1[oldest[0]]
        self._l1[key] = {"data": data, "expire": time.time() + self._ttl}

    def clear(self):
        """清空缓存"""
        self._l1.clear()
        if self._redis:
            # 只清除 rag_cache: 前缀的 key
            for key in self._redis.scan_iter("rag_cache:*"):
                self._redis.delete(key)

    def stats(self) -> dict:
        """缓存统计"""
        return {
            "l1_size": len(self._l1),
            "l2_available": self._redis is not None,
            "max_size": self._max_size,
            "ttl": self._ttl,
        }
