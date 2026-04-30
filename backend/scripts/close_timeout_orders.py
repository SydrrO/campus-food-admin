from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from redis.exceptions import RedisError

from app.db.base import SessionLocal
from app.services.order_lifecycle import close_due_orders_from_redis, close_expired_orders
from app.services.redis_timeout import get_redis_client


def main() -> None:
    db = SessionLocal()
    try:
        try:
            redis_client = get_redis_client()
            closed_order_nos = close_due_orders_from_redis(db, redis_client)
        except RedisError:
            closed_order_nos = close_expired_orders(db)
        print({
            "closed_orders": closed_order_nos,
            "count": len(closed_order_nos),
            "auto_close_enabled": True,
        })
    finally:
        db.close()


if __name__ == "__main__":
    main()
