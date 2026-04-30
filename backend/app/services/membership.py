from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Order, OrderStatus, User


PAID_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
}

LEVEL_TARGETS = {
    1: Decimal("100.00"),
    2: Decimal("300.00"),
    3: Decimal("700.00"),
}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def get_paid_spend(db: Session, user_id: int) -> Decimal:
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.total_spent is not None:
        return Decimal(str(user.total_spent or "0.00")).quantize(Decimal("0.01"))

    total = (
        db.query(Order)
        .filter(Order.user_id == user_id, Order.status.in_(PAID_ORDER_STATUSES))
        .all()
    )
    return sum((Decimal(str(order.actual_amount)) for order in total), Decimal("0.00")).quantize(Decimal("0.01"))


def record_order_spend(db: Session, order: Order) -> None:
    if order.spend_counted_at is not None or order.paid_at is None:
        return

    user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
    if not user:
        return

    user.total_spent = Decimal(str(user.total_spent or "0.00")) + Decimal(str(order.actual_amount or "0.00"))
    order.spend_counted_at = order.paid_at
    db.add(user)
    db.add(order)


def recalculate_user_total_spent(db: Session, user_id: int) -> None:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        return

    paid_orders = (
        db.query(Order)
        .filter(Order.user_id == user_id, Order.status.in_(PAID_ORDER_STATUSES))
        .all()
    )
    user.total_spent = sum(
        (Decimal(str(order.actual_amount or "0.00")) for order in paid_orders),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    db.add(user)


def build_membership_state(db: Session, user: User) -> dict:
    total_spent = get_paid_spend(db, int(user.id))

    if not user.is_member:
        return {
            "member_level": "LV0",
            "member_level_value": 0,
            "total_spent": _money(total_spent),
            "next_member_level": "LV1",
            "next_level_spend": _money(LEVEL_TARGETS[1]),
            "amount_to_next_level": _money(max(LEVEL_TARGETS[1] - total_spent, Decimal("0.00"))),
            "level_progress_percent": min(int((total_spent / LEVEL_TARGETS[1]) * 100), 100),
            "weekly_coupon_count": 0,
            "level_benefit_text": "开通会员后积分可兑换抵扣券",
        }

    level = 1
    if total_spent >= LEVEL_TARGETS[2]:
        level = 2
    if total_spent >= LEVEL_TARGETS[3]:
        level = 3

    next_level = level + 1 if level < 3 else None
    next_target = LEVEL_TARGETS.get(next_level) if next_level else None
    amount_to_next = max((next_target or total_spent) - total_spent, Decimal("0.00"))
    progress_percent = 100
    if next_target:
        previous_target = Decimal("0.00") if level == 1 else LEVEL_TARGETS.get(level, Decimal("0.00"))
        span = max(next_target - previous_target, Decimal("1.00"))
        progress_percent = min(
            int(((total_spent - previous_target) / span) * 100),
            100,
        )
        progress_percent = max(progress_percent, 0)

    return {
        "member_level": f"LV{level}",
        "member_level_value": level,
        "total_spent": _money(total_spent),
        "next_member_level": f"LV{next_level}" if next_level else None,
        "next_level_spend": _money(next_target) if next_target else None,
        "amount_to_next_level": _money(amount_to_next),
        "level_progress_percent": progress_percent,
        "weekly_coupon_count": level,
        "level_benefit_text": f"LV{level} 积分可兑换抵扣券",
    }
