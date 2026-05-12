from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Address, Dish, Order, OrderItem, OrderStatus, SystemConfig, User, UserCoupon
from app.schemas.order import OrderCreateIn, OrderCreateOut, OrderDetailOut, OrderItemOut, OrderSummaryOut
from app.schemas.response import ResponseModel
from app.services.membership import record_order_spend
from app.services.order_lifecycle import (
    close_expired_orders,
    close_order,
    get_order_expire_time,
    get_payment_timeout_minutes,
    is_order_expired,
)
from app.services.redis_timeout import clear_order_timeout, get_redis_client, track_order_timeout
from app.utils.order_no import generate_order_no
from app.utils.timezone import now_china

router = APIRouter()

SPECIAL_COUPON_ACCOUNTED_USER_IDS = {1, 2, 5, 92}


def _get_config_map(db: Session) -> dict[str, str]:
    configs = db.query(SystemConfig).all()
    return {config.config_key: config.config_value for config in configs}


def _parse_deadline(value: str, fallback: str) -> time:
    raw = value or fallback
    hour, minute = raw.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _build_delivery_address(address: Address) -> str:
    parts = [address.building]
    if address.room_number:
        parts.append(address.room_number)
    parts.append(address.detail_address)
    return " ".join(part for part in parts if part)


def _get_delivery_fee(config_map: dict[str, str], address: Address, user: User) -> Decimal:
    if user.is_member:
        return Decimal("0.00")

    return Decimal(config_map.get("base_delivery_fee", "1") or "1")


def _get_member_discount_amount(user: User, delivery_date: date, total_amount: Decimal) -> Decimal:
    if not user.is_member or delivery_date.weekday() != 5:
        return Decimal("0.00")
    return (total_amount * Decimal("0.05")).quantize(Decimal("0.01"))


def _resolve_coupon_for_order(db: Session, user: User, coupon_id: int | None) -> tuple[UserCoupon | None, Decimal, ResponseModel | None]:
    if coupon_id is None:
        return None, Decimal("0.00"), None

    coupon = (
        db.query(UserCoupon)
        .filter(UserCoupon.id == coupon_id, UserCoupon.user_id == user.id)
        .with_for_update()
        .first()
    )
    if not coupon:
        return None, Decimal("0.00"), ResponseModel(code=404, message="Coupon not found", data=None)
    if coupon.status not in {"unrevealed", "available"}:
        return None, Decimal("0.00"), ResponseModel(code=400, message="Coupon cannot be used", data=None)

    if coupon.status == "unrevealed":
        coupon.status = "available"
        coupon.title = "0.5元券"
        coupon.amount = Decimal("0.50")
        coupon.revealed_at = now_china()

    amount = Decimal(str(coupon.amount or "0.00"))
    return coupon, amount, None


def _get_allowed_delivery_options(now: datetime, lunch_deadline: time, dinner_deadline: time) -> set[tuple[date, str]]:
    today = now.date()
    tomorrow = today + timedelta(days=1)
    current_time = now.time()

    if current_time < lunch_deadline:
        return {(today, "lunch"), (today, "dinner")}

    if current_time < dinner_deadline:
        return {(today, "dinner")}

    return {(tomorrow, "lunch"), (tomorrow, "dinner")}


def _serialize_create_out(order: Order, expire_time: datetime | None) -> OrderCreateOut:
    return OrderCreateOut(
        order_id=order.id,
        order_no=order.order_no,
        status=order.status.value if hasattr(order.status, "value") else str(order.status),
        total_amount=str(order.total_amount.quantize(Decimal("0.01"))),
        delivery_fee=str(order.delivery_fee.quantize(Decimal("0.01"))),
        discount_amount=str((order.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))),
        actual_amount=str(order.actual_amount.quantize(Decimal("0.01"))),
        expire_time=expire_time.isoformat() if expire_time else None,
    )


def _get_create_expire_time(order: Order, timeout_minutes: int | None) -> datetime | None:
    if order.status != OrderStatus.unpaid:
        return None
    return get_order_expire_time(order, timeout_minutes)


def _clear_timeout(order_no: str) -> None:
    try:
        clear_order_timeout(get_redis_client(), order_no)
    except RedisError:
        pass


def _serialize_order_summary(order: Order, timeout_minutes: int | None = None, items: list[OrderItem] | None = None) -> OrderSummaryOut:
    expire_time = get_order_expire_time(order, timeout_minutes) if order.status == OrderStatus.unpaid else None
    raw_items = items or []
    return OrderSummaryOut(
        order_id=int(order.id),
        order_no=order.order_no,
        status=order.status.value if hasattr(order.status, "value") else str(order.status),
        meal_type=order.meal_type.value if hasattr(order.meal_type, "value") else str(order.meal_type),
        delivery_date=order.delivery_date,
        total_amount=str(order.total_amount.quantize(Decimal("0.01"))),
        delivery_fee=str(order.delivery_fee.quantize(Decimal("0.01"))),
        discount_amount=str((getattr(order, "discount_amount", Decimal("0.00")) or Decimal("0.00")).quantize(Decimal("0.01"))),
        coupon_id=int(order.coupon_id) if order.coupon_id else None,
        actual_amount=str(order.actual_amount.quantize(Decimal("0.01"))),
        contact_name=order.contact_name,
        contact_phone=order.contact_phone,
        delivery_address=order.delivery_address,
        remark=order.remark,
        created_at=order.created_at.isoformat() if order.created_at else None,
        expire_time=expire_time.isoformat() if expire_time else None,
        items=[OrderItemOut(
            dish_id=int(item.dish_id),
            dish_name=item.dish_name,
            dish_image=item.dish_image,
            price=str(item.price.quantize(Decimal("0.01"))),
            quantity=item.quantity,
            subtotal=str(item.subtotal.quantize(Decimal("0.01"))),
        ) for item in raw_items],
    )


def _serialize_order_detail(order: Order, items: list[OrderItem], timeout_minutes: int | None = None) -> OrderDetailOut:
    summary = _serialize_order_summary(order, timeout_minutes)
    return OrderDetailOut(**summary.model_dump())

@router.post("", response_model=ResponseModel[OrderCreateOut])
async def create_order(
    payload: OrderCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建订单，校验日期、截止时间、地址归属和菜品状态。"""
    if not payload.items:
        return ResponseModel(code=400, message="Order items cannot be empty", data=None)

    if payload.meal_type not in {"lunch", "dinner"}:
        return ResponseModel(code=400, message="Invalid meal type", data=None)

    config_map = _get_config_map(db)
    timeout_minutes = get_payment_timeout_minutes(config_map)
    idempotency_key = (payload.idempotency_key or "").strip()[:64] or None
    if idempotency_key:
        existing_order = (
            db.query(Order)
            .filter(Order.user_id == current_user.id, Order.idempotency_key == idempotency_key)
            .first()
        )
        if existing_order:
            if existing_order.status == OrderStatus.unpaid and is_order_expired(existing_order, timeout_minutes):
                close_order(db, existing_order)
                db.commit()
                db.refresh(existing_order)
                _clear_timeout(existing_order.order_no)
            return ResponseModel(data=_serialize_create_out(existing_order, _get_create_expire_time(existing_order, timeout_minutes)))

    lunch_deadline = _parse_deadline(config_map.get("lunch_deadline", "10:00"), "10:00")
    dinner_deadline = _parse_deadline(config_map.get("dinner_deadline", "16:00"), "16:00")
    allowed_delivery_options = _get_allowed_delivery_options(
        now_china(),
        lunch_deadline,
        dinner_deadline,
    )
    if (payload.delivery_date, payload.meal_type) not in allowed_delivery_options:
        return ResponseModel(code=400, message="Selected delivery slot is no longer available", data=None)

    address = (
        db.query(Address)
        .filter(Address.id == payload.address_id, Address.user_id == current_user.id)
        .first()
    )
    if not address:
        return ResponseModel(code=404, message="Address not found", data=None)

    total_amount = Decimal("0.00")
    order_items: list[OrderItem] = []
    for item in payload.items:
        if item.quantity <= 0:
            return ResponseModel(code=400, message="Quantity must be greater than 0", data=None)

        dish = db.query(Dish).filter(Dish.id == item.dish_id).with_for_update().first()
        if not dish or not dish.is_active:
            return ResponseModel(code=404, message=f"Dish {item.dish_id} not found", data=None)

        if dish.is_sold_out:
            return ResponseModel(code=400, message=f"Dish {dish.name} is sold out", data=None)

        if dish.stock is not None and dish.stock >= 0 and dish.stock < item.quantity:
            return ResponseModel(code=400, message=f"Dish {dish.name} stock is insufficient", data=None)

        if dish.stock is not None and dish.stock >= 0:
            dish.stock -= item.quantity

        price = Decimal(str(dish.price))
        cost_price = Decimal(str(dish.cost_price or "0.00"))
        subtotal = (price * item.quantity).quantize(Decimal("0.01"))
        total_amount += subtotal
        order_items.append(
            OrderItem(
                dish_id=dish.id,
                dish_name=dish.name,
                dish_image=dish.image_url,
                price=price,
                cost_price=cost_price,
                quantity=item.quantity,
                flavors=item.flavors,
                subtotal=subtotal,
            )
        )

    delivery_fee = _get_delivery_fee(config_map, address, current_user)
    member_discount_amount = _get_member_discount_amount(current_user, payload.delivery_date, total_amount)
    selected_coupon, coupon_discount_amount, coupon_error = _resolve_coupon_for_order(db, current_user, payload.coupon_id)
    if coupon_error:
        return coupon_error

    payable_amount = (total_amount + delivery_fee).quantize(Decimal("0.01"))
    requested_discount_amount = member_discount_amount + coupon_discount_amount
    discount_amount = min(requested_discount_amount, payable_amount).quantize(Decimal("0.01"))
    actual_amount = (payable_amount - discount_amount).quantize(Decimal("0.01"))
    is_special_coupon_accounted_order = int(current_user.id) in SPECIAL_COUPON_ACCOUNTED_USER_IDS and selected_coupon is not None
    if is_special_coupon_accounted_order:
        discount_amount = Decimal("0.00")
        actual_amount = payable_amount
    is_zero_pay_order = actual_amount <= Decimal("0.00")
    is_direct_confirm_order = is_zero_pay_order or is_special_coupon_accounted_order
    order_no = generate_order_no()
    created_at = now_china()
    order = Order(
        order_no=order_no,
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        contact_name=address.contact_name,
        contact_phone=address.contact_phone,
        delivery_address=_build_delivery_address(address),
        meal_type=payload.meal_type,
        delivery_date=payload.delivery_date,
        total_amount=total_amount,
        delivery_fee=delivery_fee,
        discount_amount=discount_amount,
        actual_amount=actual_amount,
        status=OrderStatus.confirmed if is_direct_confirm_order else OrderStatus.unpaid,
        remark=payload.remark,
        coupon_id=int(selected_coupon.id) if selected_coupon else None,
        pay_method="coupon_accounted" if is_special_coupon_accounted_order else (("coupon" if selected_coupon else "discount") if is_zero_pay_order else None),
        paid_at=created_at if is_direct_confirm_order else None,
        created_at=created_at,
    )
    db.add(order)
    db.flush()

    if selected_coupon and is_direct_confirm_order:
        selected_coupon.status = "used"
        selected_coupon.used_at = created_at
        selected_coupon.locked_order_id = order.id
        db.add(selected_coupon)
    elif selected_coupon:
        selected_coupon.status = "reserved"
        selected_coupon.locked_order_id = order.id
        db.add(selected_coupon)

    for order_item in order_items:
        order_item.order_id = order.id
        db.add(order_item)

    if is_direct_confirm_order:
        record_order_spend(db, order)

    db.commit()
    db.refresh(order)

    expire_time = _get_create_expire_time(order, timeout_minutes)
    if order.status == OrderStatus.unpaid:
        try:
            redis_client = get_redis_client()
            track_order_timeout(
                redis_client,
                order.order_no,
                timeout_minutes * 60,
            )
        except RedisError:
            pass

    return ResponseModel(
        data=_serialize_create_out(order, expire_time)
    )


@router.get("", response_model=ResponseModel[list[OrderSummaryOut]])
async def list_orders(
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户订单列表。"""
    close_expired_orders(db)
    query = db.query(Order).filter(Order.user_id == current_user.id)
    if status:
        query = query.filter(Order.status == status)

    orders = (
        query.order_by(Order.created_at.desc())
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
        .all()
    )

    # Bulk load items for all orders
    order_ids = [o.id for o in orders]
    all_items = db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).order_by(OrderItem.id.asc()).all() if order_ids else []
    items_by_order = {}
    for item in all_items:
        items_by_order.setdefault(item.order_id, []).append(item)

    timeout_minutes = get_payment_timeout_minutes(_get_config_map(db))
    return ResponseModel(data=[_serialize_order_summary(order, timeout_minutes, items_by_order.get(order.id, [])) for order in orders])


@router.get("/{order_no}", response_model=ResponseModel[OrderDetailOut])
async def get_order_detail(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取订单详情。"""
    close_expired_orders(db)
    order = db.query(Order).filter(Order.order_no == order_no, Order.user_id == current_user.id).first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    timeout_minutes = get_payment_timeout_minutes(_get_config_map(db))
    return ResponseModel(data=_serialize_order_detail(order, items, timeout_minutes))


@router.post("/{order_no}/cancel", response_model=ResponseModel[OrderDetailOut])
async def cancel_order(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消未支付订单，并回滚库存。"""
    config_map = _get_config_map(db)
    timeout_minutes = get_payment_timeout_minutes(config_map)
    order = (
        db.query(Order)
        .filter(Order.order_no == order_no, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)
    if order.status != OrderStatus.unpaid:
        return ResponseModel(code=400, message="Only unpaid orders can be cancelled", data=None)
    if is_order_expired(order, timeout_minutes):
        close_order(db, order, closed_at=now_china())
        db.commit()
        db.refresh(order)
        _clear_timeout(order.order_no)
        return ResponseModel(code=400, message="订单已超过15分钟支付/取消时间，已自动关闭", data=None)

    close_order(db, order, closed_at=now_china())
    db.commit()
    db.refresh(order)
    _clear_timeout(order.order_no)

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items, timeout_minutes))
