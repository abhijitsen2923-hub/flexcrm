import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, datetime | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            value = self._store.get(key)
            if value is None:
                return None
            payload, expires_at = value
            if expires_at and expires_at <= datetime.now(UTC):
                self._store.pop(key, None)
                return None
            return payload

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        async with self._lock:
            self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def delete_pattern(self, prefix: str) -> None:
        async with self._lock:
            for key in list(self._store.keys()):
                if key.startswith(prefix):
                    self._store.pop(key, None)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        async with self._lock:
            value = self._store.get(key)
            counter = 1
            if value is not None:
                payload, expires_at = value
                if not expires_at or expires_at > datetime.now(UTC):
                    counter = int(payload or 0) + 1
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
            self._store[key] = (counter, expires_at)
            return counter


class CacheClient:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._fallback = InMemoryCache()

    async def connect(self) -> None:
        settings = get_settings()
        try:
            self._redis = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                # Bound the pool per instance so multiple Cloud Run instances stay
                # under the Redis Cloud free-tier ~30-connection cap (2 instances
                # x 12 = 24). Redis ops are sub-ms, so the pool sustains high
                # throughput via reuse; rare overflow hits the fail-open path.
                max_connections=12,
                health_check_interval=30,
            )
            await self._redis.ping()
            logger.info("Connected to Redis cache")
        except RedisError as exc:
            self._redis = None
            # The in-memory fallback is per-process; it makes rate limiting and
            # cache invalidation incorrect across multiple workers/replicas.
            # In production we refuse to start rather than degrade silently.
            if settings.environment == "production":
                raise RuntimeError(
                    "Redis is required in production (REDIS_URL is unreachable). "
                    "Provision Redis or set ENVIRONMENT to a non-production value."
                ) from exc
            logger.warning(
                "Redis is unavailable; falling back to in-memory cache. "
                "Safe only for a single Uvicorn worker."
            )

    async def disconnect(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def get_json(self, key: str) -> Any | None:
        if self._redis is None:
            return await self._fallback.get(key)
        try:
            payload = await self._redis.get(key)
            return json.loads(payload) if payload else None
        except RedisError as exc:
            # Fail open: a Redis blip (or hitting a free-tier limit) becomes a
            # cache miss, not a 500. The caller falls through to the database.
            logger.warning("Redis get(%s) failed; treating as cache miss: %s", key, exc)
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if self._redis is None:
            await self._fallback.set(key, value, ttl_seconds)
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl_seconds)
        except RedisError as exc:
            logger.warning("Redis set(%s) failed; skipping cache write: %s", key, exc)

    async def delete(self, key: str) -> None:
        if self._redis is None:
            await self._fallback.delete(key)
            return
        try:
            await self._redis.delete(key)
        except RedisError as exc:
            logger.warning("Redis delete(%s) failed; skipping: %s", key, exc)

    async def delete_pattern(self, prefix: str) -> None:
        if self._redis is None:
            await self._fallback.delete_pattern(prefix)
            return
        try:
            pattern = f"{prefix}*"
            async for key in self._scan_iter(pattern):
                await self._redis.delete(key)
        except RedisError as exc:
            logger.warning("Redis delete_pattern(%s) failed; skipping invalidation: %s", prefix, exc)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        if self._redis is None:
            return await self._fallback.increment(key, ttl_seconds)
        try:
            async with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, ttl_seconds)
                result = await pipeline.execute()
            return int(result[0])
        except RedisError as exc:
            # Fail open: if we can't reach Redis, don't block the request.
            # Returning 0 keeps the caller under any rate limit.
            logger.warning("Redis increment(%s) failed; failing open: %s", key, exc)
            return 0

    async def _scan_iter(self, match: str) -> AsyncIterator[str]:
        if self._redis is None:
            return
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=match, count=100)
            for key in keys:
                yield key
            if cursor == 0:
                break


cache_client = CacheClient()
