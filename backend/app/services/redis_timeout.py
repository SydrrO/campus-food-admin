from __future__ import annotations

import time

import redis

from app.core.config import settings


TIMEOUT_QUEUE_KEY = "order:timeout:queue"


def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,
    )


def track_order_timeout(redis_client: redis.Redis, order_no: str, expire_seconds: int) -> None:
    expire_at = int(time.time()) + expire_seconds
    redis_client.setex(f"order:timeout:{order_no}", expire_seconds, order_no)
    redis_client.zadd(TIMEOUT_QUEUE_KEY, {order_no: expire_at})


def clear_order_timeout(redis_client: redis.Redis, order_no: str) -> None:
    redis_client.delete(f"order:timeout:{order_no}")
    redis_client.zrem(TIMEOUT_QUEUE_KEY, order_no)


def list_due_order_nos(redis_client: redis.Redis, now_ts: int | None = None) -> list[str]:
    timestamp = now_ts or int(time.time())
    return list(redis_client.zrangebyscore(TIMEOUT_QUEUE_KEY, min=0, max=timestamp))
