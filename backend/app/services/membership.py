from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import Order, OrderStatus, User


PAID_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
}

LEVEL_TARGETS = {
    1: Decimal("0.00"),
    2: Decimal("100.00"),
    3: Decimal("250.00"),
    4: Decimal("550.00"),
    5: Decimal("800.00"),
}

LEVEL_NAMES = {
    0: {"title": "普通用户", "short": ""},
    1: {"title": "黑铁会员", "short": "黑铁"},
    2: {"title": "白银会员", "short": "白银"},
    3: {"title": "黄金会员", "short": "黄金"},
    4: {"title": "铂金会员", "short": "铂金"},
    5: {"title": "钻石会员", "short": "钻石"},
}

LEVEL_COLORS = {
    0: {"primary": "#B0B0B0", "gradient": "linear-gradient(135deg, #C8C8C8 0%, #A0A0A0 100%)", "badge": "#9E9E9E", "glow": "rgba(176, 176, 176, 0.28)"},
    1: {"primary": "#7B7B7B", "gradient": "linear-gradient(135deg, #A5A5A5 0%, #5E5E5E 100%)", "badge": "#5A5A5A", "glow": "rgba(120, 120, 120, 0.26)"},
    2: {"primary": "#9BA3AE", "gradient": "linear-gradient(135deg, #D8DDE3 0%, #9BA3AE 100%)", "badge": "#8E97A2", "glow": "rgba(168, 176, 184, 0.28)"},
    3: {"primary": "#D4A017", "gradient": "linear-gradient(135deg, #F0D68A 0%, #C59B0E 100%)", "badge": "#C59B0E", "glow": "rgba(212, 160, 23, 0.32)"},
    4: {"primary": "#4DB6AC", "gradient": "linear-gradient(135deg, #8ED6CC 0%, #3D9D93 100%)", "badge": "#3D9D93", "glow": "rgba(77, 182, 172, 0.30)"},
    5: {"primary": "#6C8EE0", "gradient": "linear-gradient(135deg, #A8C4F4 0%, #5175C0 100%)", "badge": "#5175C0", "glow": "rgba(108, 142, 224, 0.34)"},
}

LEVEL_BENEFITS = {
    0: "开通会员享受专属权益",
    1: "黑铁会员 · 积分可兑换抵扣券",
    2: "白银会员 · 享双倍积分权益",
    3: "黄金会员 · 享三倍积分权益",
    4: "铂金会员 · 享专属客服权益",
    5: "钻石会员 · 享专属客服 + 五倍积分",
}

POINTS_PER_YUAN = Decimal("100")


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _points_for_amount(value) -> int:
    amount = Decimal(str(value or "0.00"))
    return int((amount * POINTS_PER_YUAN).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _amount(value) -> Decimal:
    return Decimal(str(value or "0.00")).quantize(Decimal("0.01"))


def _points_basis(order: Order) -> Decimal:
    return (_amount(order.actual_amount) + _amount(getattr(order, "discount_amount", Decimal("0.00")))).quantize(Decimal("0.01"))


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

    order_amount = _amount(order.actual_amount)
    points_amount = _points_basis(order)
    user.total_spent = Decimal(str(user.total_spent or "0.00")) + order_amount
    user.points = int(user.points or 0) + _points_for_amount(points_amount)
    order.spend_counted_at = order.paid_at
    db.add(user)
    db.add(order)


def reverse_order_spend(db: Session, order: Order) -> None:
    if order.spend_counted_at is None:
        return

    user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
    if not user:
        return

    order_amount = _amount(order.actual_amount)
    points_amount = _points_basis(order)
    user.total_spent = max(
        Decimal(str(user.total_spent or "0.00")) - order_amount,
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    user.points = max(int(user.points or 0) - _points_for_amount(points_amount), 0)
    order.spend_counted_at = None
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
    order_amounts = [Decimal(str(order.actual_amount or "0.00")) for order in paid_orders]
    user.total_spent = sum(order_amounts, Decimal("0.00")).quantize(Decimal("0.01"))
    db.add(user)


MAX_LEVEL = max(LEVEL_TARGETS.keys())


def _resolve_level(total_spent):
    for lv in sorted(LEVEL_TARGETS.keys(), reverse=True):
        if total_spent >= LEVEL_TARGETS[lv]:
            return lv
    return 0


def _level_name(lv):
    return LEVEL_NAMES.get(lv, LEVEL_NAMES[0])


def _level_color(lv):
    return LEVEL_COLORS.get(lv, LEVEL_COLORS[0])


def _level_benefit(lv):
    return LEVEL_BENEFITS.get(lv, LEVEL_BENEFITS[0])


def build_membership_state(db: Session, user: User) -> dict:
    total_spent = get_paid_spend(db, int(user.id))

    if not user.is_member:
        return {
            "member_level": "普通用户",
            "member_level_value": 0,
            "total_spent": _money(total_spent),
            "next_member_level": LEVEL_NAMES[1]["title"],
            "next_level_spend": _money(LEVEL_TARGETS[1]),
            "amount_to_next_level": _money(max(LEVEL_TARGETS[1] - total_spent, Decimal("0.00"))),
            "level_progress_percent": min(int((total_spent / LEVEL_TARGETS[2]) * 100), 100),
            "weekly_coupon_count": 0,
            "level_benefit_text": LEVEL_BENEFITS[0],
            "level_color": _level_color(0),
            "level_name": _level_name(0),
        }

    level = _resolve_level(total_spent)

    next_level = level + 1 if level < MAX_LEVEL else None
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
        "member_level": LEVEL_NAMES[level]["title"],
        "member_level_value": level,
        "total_spent": _money(total_spent),
        "next_member_level": LEVEL_NAMES[next_level]["title"] if next_level else None,
        "next_level_spend": _money(next_target) if next_target else None,
        "amount_to_next_level": _money(amount_to_next),
        "level_progress_percent": progress_percent,
        "weekly_coupon_count": level,
        "level_benefit_text": _level_benefit(level),
        "level_color": _level_color(level),
        "level_name": _level_name(level),
    }
