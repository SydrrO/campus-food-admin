from __future__ import annotations

import asyncio

from redis.exceptions import RedisError

from app.db.base import SessionLocal
from app.services.order_lifecycle import close_due_orders_from_redis, close_expired_orders
from app.services.redis_timeout import get_redis_client


async def timeout_order_loop(interval_seconds: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            redis_client = get_redis_client()
            close_due_orders_from_redis(db, redis_client)
        except RedisError:
            close_expired_orders(db)
        finally:
            db.close()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


def start_timeout_worker(interval_seconds: int) -> tuple[asyncio.Task[None], asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(timeout_order_loop(interval_seconds, stop_event))
    return task, stop_event
