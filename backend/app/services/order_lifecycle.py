from datetime import datetime, timedelta

from redis import Redis
from sqlalchemy.orm import Session

from app.models import Dish, Order, OrderItem, OrderStatus, SystemConfig, UserCoupon
from app.services.redis_timeout import clear_order_timeout, list_due_order_nos
from app.utils.timezone import now_china

DEFAULT_PAYMENT_TIMEOUT_MINUTES = 15


def get_config_map(db: Session) -> dict[str, str]:
    configs = db.query(SystemConfig).all()
    return {config.config_key: config.config_value for config in configs}


def get_payment_timeout_minutes(config_map: dict[str, str] | None = None) -> int:
    raw = (config_map or {}).get("payment_timeout", str(DEFAULT_PAYMENT_TIMEOUT_MINUTES))
    try:
        value = int(raw or DEFAULT_PAYMENT_TIMEOUT_MINUTES)
    except (TypeError, ValueError):
        value = DEFAULT_PAYMENT_TIMEOUT_MINUTES
    return max(value, 1)


def get_order_expire_time(order: Order, timeout_minutes: int | None = None) -> datetime | None:
    if not order.created_at:
        return None
    minutes = timeout_minutes or DEFAULT_PAYMENT_TIMEOUT_MINUTES
    return order.created_at + timedelta(minutes=minutes)


def is_order_expired(order: Order, timeout_minutes: int | None = None, now: datetime | None = None) -> bool:
    expire_time = get_order_expire_time(order, timeout_minutes)
    return bool(expire_time and (now or now_china()) >= expire_time)


def release_order_stock(db: Session, order: Order) -> list[OrderItem]:
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    for item in items:
        dish = db.query(Dish).filter(Dish.id == item.dish_id).with_for_update().first()
        if dish and dish.stock is not None and dish.stock >= 0:
            dish.stock += item.quantity
    return items


def close_order(db: Session, order: Order, closed_at: datetime | None = None) -> list[OrderItem]:
    if order.status == OrderStatus.closed:
        return []

    items = release_order_stock(db, order)
    if order.coupon_id:
        coupon = db.query(UserCoupon).filter(UserCoupon.id == order.coupon_id).first()
        if coupon and coupon.status == "reserved":
            coupon.status = "available"
            coupon.locked_order_id = None
            db.add(coupon)
    order.status = OrderStatus.closed
    order.closed_at = closed_at or now_china()
    db.add(order)
    return items


def close_expired_orders(db: Session) -> list[str]:
    timeout_minutes = get_payment_timeout_minutes(get_config_map(db))
    deadline = now_china() - timedelta(minutes=timeout_minutes)
    expired_orders = (
        db.query(Order)
        .filter(Order.status == OrderStatus.unpaid, Order.created_at <= deadline)
        .with_for_update()
        .all()
    )

    closed_order_nos: list[str] = []
    for order in expired_orders:
        close_order(db, order)
        closed_order_nos.append(order.order_no)

    if closed_order_nos:
        db.commit()
    return closed_order_nos


def close_due_orders_from_redis(db: Session, redis_client: Redis) -> list[str]:
    due_order_nos = list_due_order_nos(redis_client)
    if not due_order_nos:
        return close_expired_orders(db)

    closed_order_nos: list[str] = []
    for order_no in due_order_nos:
        order = (
            db.query(Order)
            .filter(Order.order_no == order_no)
            .with_for_update()
            .first()
        )
        if order and order.status == OrderStatus.unpaid:
            close_order(db, order)
            closed_order_nos.append(order_no)
        clear_order_timeout(redis_client, order_no)

    if closed_order_nos:
        db.commit()

    db_closed_order_nos = close_expired_orders(db)
    return closed_order_nos + db_closed_order_nos
