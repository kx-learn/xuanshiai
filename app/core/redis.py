"""Redis helpers for discovery caches and daily quotas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def consume_daily(key: str, limit: int) -> bool:
    """Atomically consume one daily quota item, failing closed if Redis is unavailable."""
    try:
        value = await redis_client.incr(key)
        if value == 1:
            seconds_until_reset = int(
                (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                 + timedelta(days=1) - datetime.now(UTC)).total_seconds()
            )
            await redis_client.expire(key, max(60, seconds_until_reset))
        if value > limit:
            await redis_client.decr(key)
            return False
        return True
    except RedisError as exc:
        raise HTTPException(503, detail="Redis服务未配置或暂时不可用") from exc


async def refund_daily(key: str) -> None:
    try:
        value = await redis_client.get(key)
        if value and int(value) > 0:
            await redis_client.decr(key)
    except RedisError as exc:
        raise HTTPException(503, detail="Redis服务未配置或暂时不可用") from exc
