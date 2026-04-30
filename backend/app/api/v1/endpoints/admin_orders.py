from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import settings
from app.db.session import get_db
from app.models import Admin, Category, Dish, Order, OrderItem, OrderStatus, SystemConfig, User
from app.schemas.admin_order import (
    AdminOperationsOverviewOut,
    AdminOrderDetailOut,
    AdminOrderMonitorOut,
    AdminRefundTraceOut,
    AdminOrderSummaryOut,
    CountBreakdownOut,
    OperationsTrendPointOut,
    OrderStatisticsOut,
)
from app.schemas.order import OrderItemOut
from app.schemas.response import ResponseModel
from app.services.membership import recalculate_user_total_spent
from app.services.refund_trace import apply_wechat_trade_trace
from app.services.wechat_pay import (
    WechatPayConfigError,
    WechatPayError,
    WechatPayRequestError,
    _amount_to_fen,
    get_wechat_pay_mode,
    is_wechat_pay_real_mode,
    query_trade_state,
)
from app.utils.timezone import now_china, today_china


router = APIRouter()

STATUS_LABELS = {
    "unpaid": "待支付",
    "confirmed": "已确认",
    "delivering": "处理中",
    "completed": "已完成",
    "closed": "已关闭",
    "refunded": "已退款",
}

MEAL_TYPE_LABELS = {
    "lunch": "午餐",
    "dinner": "晚餐",
}

PAID_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
}

ACTIVE_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
}

REFUND_TRACE_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
    OrderStatus.refunded,
}

MANUAL_REFUND_ALLOWED_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
}


def _is_paid_order(order: Order) -> bool:
    return bool(order.paid_at and order.status in PAID_ORDER_STATUSES)


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _serialize_item_summary(items: list[OrderItem] | None) -> tuple[str | None, int]:
    if not items:
        return None, 0
    total_quantity = sum(int(item.quantity or 0) for item in items)
    summary = "，".join(f"{item.dish_name}x{item.quantity}" for item in items)
    return summary, total_quantity


def _load_order_items(db: Session, order: Order) -> list[OrderItem]:
    return db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()


def _serialize_order_summary(order: Order, items: list[OrderItem] | None = None) -> AdminOrderSummaryOut:
    item_summary, item_count = _serialize_item_summary(items)
    return AdminOrderSummaryOut(
        order_id=int(order.id),
        order_no=order.order_no,
        user_id=int(order.user_id),
        status=_enum_value(order.status),
        meal_type=_enum_value(order.meal_type),
        delivery_date=order.delivery_date,
        total_amount=str(order.total_amount),
        delivery_fee=str(order.delivery_fee),
        actual_amount=str(order.actual_amount),
        item_summary=item_summary,
        item_count=item_count,
        contact_name=order.contact_name,
        contact_phone=order.contact_phone,
        delivery_address=order.delivery_address,
        remark=order.remark,
        wechat_trade_state=order.wechat_trade_state,
        refund_checked_at=order.refund_checked_at.isoformat() if order.refund_checked_at else None,
        refunded_at=order.refunded_at.isoformat() if order.refunded_at else None,
        created_at=order.created_at.isoformat() if order.created_at else None,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )


def _format_flavors(item: OrderItem) -> str:
    if not item.flavors:
        return ""
    if isinstance(item.flavors, dict):
        pairs = []
        for key, value in item.flavors.items():
            if value in (None, "", [], {}):
                continue
            pairs.append(f"{key}: {value}")
        return f" ({'; '.join(pairs)})" if pairs else ""
    return f" ({item.flavors})"


def _build_order_record_text(order: Order, items: list[OrderItem]) -> str:
    status_key = _enum_value(order.status)
    meal_type_key = _enum_value(order.meal_type)
    lines = [
        "赛杜甄选订单记录",
        f"订单号: {order.order_no}",
        f"订单状态: {STATUS_LABELS.get(status_key, status_key)}",
        f"下单时间: {order.created_at.isoformat() if order.created_at else '-'}",
        f"支付时间: {order.paid_at.isoformat() if order.paid_at else '-'}",
        f"配送日期: {order.delivery_date} / {MEAL_TYPE_LABELS.get(meal_type_key, meal_type_key)}",
        f"联系人: {order.contact_name}",
        f"联系电话: {order.contact_phone}",
        f"配送地址: {order.delivery_address}",
        f"备注: {order.remark or '-'}",
        "商品明细:",
    ]
    for item in items:
        flavor_text = _format_flavors(item)
        lines.append(
            f"- {item.dish_name} x {item.quantity} | 单价 ¥{item.price} | 小计 ¥{item.subtotal}{flavor_text}"
        )
    lines.extend(
        [
            f"商品总额: ¥{order.total_amount}",
            f"配送费: ¥{order.delivery_fee}",
            f"实付金额: ¥{order.actual_amount}",
            f"支付方式: {order.pay_method or '-'}",
            f"支付单号: {order.transaction_id or '-'}",
            f"微信交易状态: {order.wechat_trade_state or '-'}",
            f"微信交易说明: {order.wechat_trade_state_desc or '-'}",
            f"退款核验时间: {order.refund_checked_at.isoformat() if order.refund_checked_at else '-'}",
            f"退款时间: {order.refunded_at.isoformat() if order.refunded_at else '-'}",
        ]
    )
    return "\n".join(lines)


def _serialize_order_detail(order: Order, items: list[OrderItem]) -> AdminOrderDetailOut:
    summary = _serialize_order_summary(order, items)
    return AdminOrderDetailOut(
        **summary.model_dump(),
        pay_method=order.pay_method,
        transaction_id=order.transaction_id,
        paid_at=order.paid_at.isoformat() if order.paid_at else None,
        closed_at=order.closed_at.isoformat() if order.closed_at else None,
        wechat_trade_state_desc=order.wechat_trade_state_desc,
        courier_id=int(order.courier_id) if order.courier_id else None,
        delivered_at=order.delivered_at.isoformat() if order.delivered_at else None,
        record_text=_build_order_record_text(order, items),
        items=[
            OrderItemOut(
                dish_id=int(item.dish_id),
                dish_name=item.dish_name,
                dish_image=item.dish_image,
                price=str(item.price),
                quantity=item.quantity,
                flavors=item.flavors,
                subtotal=str(item.subtotal),
            )
            for item in items
        ],
    )


def _build_refund_trace_out(
    order: Order,
    *,
    trade_state: str | None = None,
    trade_state_desc: str | None = None,
    transaction_id: str | None = None,
    error_message: str | None = None,
) -> AdminRefundTraceOut:
    return AdminRefundTraceOut(
        order_no=order.order_no,
        order_status=_enum_value(order.status),
        trade_state=trade_state or order.wechat_trade_state or "UNKNOWN",
        trade_state_desc=trade_state_desc if trade_state_desc is not None else order.wechat_trade_state_desc,
        transaction_id=transaction_id or order.transaction_id,
        refund_checked_at=order.refund_checked_at.isoformat() if order.refund_checked_at else None,
        refunded_at=order.refunded_at.isoformat() if order.refunded_at else None,
        mode=get_wechat_pay_mode(),
        error_message=error_message,
    )


def _validate_wechat_trade_for_order(order: Order, trade) -> str | None:
    if trade.appid != settings.WECHAT_APPID:
        return "AppID mismatch"
    if trade.mchid != settings.WECHAT_MCHID:
        return "MchID mismatch"
    if trade.currency != "CNY":
        return "Currency mismatch"
    if trade.amount_total != _amount_to_fen(order.actual_amount):
        return "Amount mismatch"
    return None


def _can_transition(order: Order, target_status: OrderStatus) -> tuple[bool, str | None]:
    if target_status == OrderStatus.confirmed:
        if order.status == OrderStatus.confirmed and order.paid_at:
            return True, None
        return False, "Only paid orders can be confirmed"
    if target_status == OrderStatus.delivering and (order.status != OrderStatus.confirmed or not order.paid_at):
        return False, "Only paid confirmed orders can be marked delivering"
    if target_status == OrderStatus.completed and order.status != OrderStatus.delivering:
        return False, "Only delivering orders can be completed"
    return True, None


def _can_manual_refund(order: Order) -> tuple[bool, str | None]:
    if order.status == OrderStatus.refunded:
        return True, None
    if order.status not in MANUAL_REFUND_ALLOWED_STATUSES:
        return False, "Only confirmed/delivering/completed orders can be manually refunded"
    if not order.paid_at:
        return False, "Only paid orders can be manually refunded"
    return True, None


def _build_order_query(
    db: Session,
    *,
    status: str | None = None,
    meal_type: str | None = None,
    delivery_date: date | None = None,
    keyword: str | None = None,
    include_refunded: bool = True,
):
    query = db.query(Order)
    if not include_refunded:
        query = query.filter(Order.status != OrderStatus.refunded)
    if status:
        if status == OrderStatus.closed.value:
            query = query.filter(Order.status.in_([OrderStatus.closed, OrderStatus.refunded]))
        else:
            query = query.filter(Order.status == status)
    if meal_type:
        query = query.filter(Order.meal_type == meal_type)
    if delivery_date:
        query = query.filter(Order.delivery_date == delivery_date)
    if keyword:
        keyword = keyword.strip()
        if keyword:
            like_keyword = f"%{keyword}%"
            query = query.filter(
                or_(
                    Order.order_no.ilike(like_keyword),
                    Order.contact_name.ilike(like_keyword),
                    Order.contact_phone.ilike(like_keyword),
                    Order.delivery_address.ilike(like_keyword),
                    Order.remark.ilike(like_keyword),
                )
            )
    return query


def _load_config_map(db: Session) -> dict[str, str]:
    return {
        item.config_key: item.config_value
        for item in db.query(SystemConfig).order_by(SystemConfig.id.asc()).all()
    }


def _sum_revenue(orders: list[Order]) -> str:
    total = sum(
        Decimal(str(order.actual_amount))
        for order in orders
        if _is_paid_order(order)
    )
    return str(total)


def _build_status_counts(orders: list[Order]) -> list[CountBreakdownOut]:
    counts = {key: 0 for key in STATUS_LABELS}
    for order in orders:
        counts[_enum_value(order.status)] = counts.get(_enum_value(order.status), 0) + 1
    return [
        CountBreakdownOut(key=key, label=label, count=counts.get(key, 0))
        for key, label in STATUS_LABELS.items()
    ]


@router.get("/operations/overview", response_model=ResponseModel[AdminOperationsOverviewOut])
async def get_operations_overview(
    snapshot_date: date | None = Query(None),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target_date = snapshot_date or today_china()
    seven_day_start = target_date - timedelta(days=6)

    today_orders = (
        db.query(Order)
        .filter(Order.delivery_date == target_date)
        .order_by(Order.created_at.desc())
        .all()
    )
    seven_day_orders = (
        db.query(Order)
        .filter(Order.delivery_date >= seven_day_start, Order.delivery_date <= target_date)
        .all()
    )
    recent_orders = db.query(Order).order_by(Order.created_at.desc()).limit(8).all()

    total_users = db.query(User).count()
    new_users_today = (
        db.query(User)
        .filter(func.date(User.created_at) == target_date.isoformat())
        .count()
    )

    category_count = db.query(Category).count()
    active_category_count = db.query(Category).filter(Category.is_active.is_(True)).count()
    dish_count = db.query(Dish).count()
    active_dish_count = db.query(Dish).filter(Dish.is_active.is_(True)).count()
    sold_out_dish_count = db.query(Dish).filter(Dish.is_sold_out.is_(True)).count()

    status_counts = _build_status_counts(today_orders)
    meal_type_counts = [
        CountBreakdownOut(
            key=meal_key,
            label=MEAL_TYPE_LABELS[meal_key],
            count=sum(1 for order in today_orders if _enum_value(order.meal_type) == meal_key),
        )
        for meal_key in MEAL_TYPE_LABELS
    ]

    trend: list[OperationsTrendPointOut] = []
    for offset in range(6, -1, -1):
        current_date = target_date - timedelta(days=offset)
        day_orders = [order for order in seven_day_orders if order.delivery_date == current_date]
        new_users = (
            db.query(User)
            .filter(func.date(User.created_at) == current_date.isoformat())
            .count()
        )
        trend.append(
            OperationsTrendPointOut(
                date=current_date,
                order_count=len(day_orders),
                revenue=_sum_revenue(day_orders),
                new_users=new_users,
            )
        )

    config_map = _load_config_map(db)

    return ResponseModel(
        data=AdminOperationsOverviewOut(
            snapshot_date=target_date,
            total_users=total_users,
            new_users_today=new_users_today,
            total_orders_today=len(today_orders),
            paid_orders_today=sum(1 for order in today_orders if _is_paid_order(order)),
            unpaid_orders_today=sum(1 for order in today_orders if order.status == OrderStatus.unpaid),
            active_orders_today=sum(1 for order in today_orders if order.status in ACTIVE_ORDER_STATUSES and _is_paid_order(order)),
            completed_orders_today=sum(1 for order in today_orders if order.status == OrderStatus.completed),
            closed_orders_today=sum(1 for order in today_orders if order.status in (OrderStatus.closed, OrderStatus.refunded)),
            today_revenue=_sum_revenue(today_orders),
            seven_day_orders=len(seven_day_orders),
            seven_day_revenue=_sum_revenue(seven_day_orders),
            category_count=category_count,
            active_category_count=active_category_count,
            dish_count=dish_count,
            active_dish_count=active_dish_count,
            sold_out_dish_count=sold_out_dish_count,
            payment_mode=get_wechat_pay_mode(),
            app_env=settings.APP_ENV,
            admin_entry="/admin/login.html",
            api_base_url="/api/v1",
            lunch_deadline=config_map.get("lunch_deadline", "10:30"),
            dinner_deadline=config_map.get("dinner_deadline", "16:00"),
            payment_timeout=config_map.get("payment_timeout", "15"),
            base_delivery_fee=config_map.get("base_delivery_fee", "0"),
            status_counts=status_counts,
            meal_type_counts=meal_type_counts,
            seven_day_trend=trend,
            recent_orders=[_serialize_order_summary(order, _load_order_items(db, order)) for order in recent_orders],
        )
    )


@router.get("/orders/statistics", response_model=ResponseModel[OrderStatisticsOut])
async def get_order_statistics(
    date: date,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    orders = db.query(Order).filter(Order.delivery_date == date).all()
    total_amount = sum(Decimal(str(order.actual_amount)) for order in orders if _is_paid_order(order))
    confirmed_orders = sum(1 for order in orders if order.status == OrderStatus.confirmed and order.paid_at)
    completed_orders = sum(1 for order in orders if order.status == OrderStatus.completed)
    return ResponseModel(
        data=OrderStatisticsOut(
            date=date,
            total_orders=len(orders),
            confirmed_orders=confirmed_orders,
            completed_orders=completed_orders,
            total_amount=str(total_amount),
        )
    )


@router.get("/orders/monitor", response_model=ResponseModel[AdminOrderMonitorOut])
async def monitor_orders(
    status: str | None = Query(None),
    meal_type: str | None = Query(None),
    delivery_date: date | None = Query(None),
    keyword: str | None = Query(None),
    include_refunded: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    base_query = _build_order_query(
        db,
        meal_type=meal_type,
        delivery_date=delivery_date,
        keyword=keyword,
        include_refunded=include_refunded,
    )
    status_scope_orders = base_query.order_by(Order.created_at.desc()).all()

    filtered_query = _build_order_query(
        db,
        status=status,
        meal_type=meal_type,
        delivery_date=delivery_date,
        keyword=keyword,
        include_refunded=include_refunded,
    )
    total = filtered_query.count()
    orders = (
        filtered_query.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ResponseModel(
        data=AdminOrderMonitorOut(
            items=[_serialize_order_summary(order, _load_order_items(db, order)) for order in orders],
            total=total,
            page=page,
            page_size=page_size,
            status_counts=_build_status_counts(status_scope_orders),
            last_updated_at=now_china().isoformat(),
        )
    )


@router.get("/orders", response_model=ResponseModel[list[AdminOrderSummaryOut]])
async def list_orders(
    status: str | None = Query(None),
    meal_type: str | None = Query(None),
    delivery_date: date | None = Query(None),
    include_refunded: bool = Query(True),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    orders = (
        _build_order_query(
            db,
            status=status,
            meal_type=meal_type,
            delivery_date=delivery_date,
            include_refunded=include_refunded,
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    return ResponseModel(data=[_serialize_order_summary(order, _load_order_items(db, order)) for order in orders])


@router.get("/orders/{order_no}", response_model=ResponseModel[AdminOrderDetailOut])
async def get_order_detail(
    order_no: str,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items))


@router.put("/orders/{order_no}/confirm", response_model=ResponseModel[AdminOrderDetailOut])
async def confirm_order(
    order_no: str,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    ok, error = _can_transition(order, OrderStatus.confirmed)
    if not ok:
        return ResponseModel(code=400, message=error or "Order confirm failed", data=None)

    order.status = OrderStatus.confirmed
    db.add(order)
    db.commit()
    db.refresh(order)
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items))


@router.put("/orders/{order_no}/delivering", response_model=ResponseModel[AdminOrderDetailOut])
async def mark_order_delivering(
    order_no: str,
    courier_id: int | None = None,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    ok, error = _can_transition(order, OrderStatus.delivering)
    if not ok:
        return ResponseModel(code=400, message=error or "Order delivering failed", data=None)

    if courier_id is not None:
        order.courier_id = courier_id
    order.status = OrderStatus.delivering
    db.add(order)
    db.commit()
    db.refresh(order)
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items))


@router.put("/orders/{order_no}/complete", response_model=ResponseModel[AdminOrderDetailOut])
async def complete_order(
    order_no: str,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    ok, error = _can_transition(order, OrderStatus.completed)
    if not ok:
        return ResponseModel(code=400, message=error or "Order complete failed", data=None)

    order.status = OrderStatus.completed
    order.delivered_at = now_china()
    db.add(order)
    db.commit()
    db.refresh(order)
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items))


@router.put("/orders/{order_no}/manual-refund", response_model=ResponseModel[AdminOrderDetailOut])
async def manual_refund_order(
    order_no: str,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).with_for_update().first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    ok, error = _can_manual_refund(order)
    if not ok:
        return ResponseModel(code=400, message=error or "Order manual refund failed", data=None)

    if order.status != OrderStatus.refunded:
        now_time = now_china()
        order.status = OrderStatus.refunded
        order.refunded_at = order.refunded_at or now_time
        order.refund_checked_at = now_time
        admin_name = getattr(current_admin, "username", None) or str(getattr(current_admin, "id", "admin"))
        order.wechat_trade_state = "MANUAL_REFUND"
        order.wechat_trade_state_desc = f"Manual refund by admin {admin_name}"
        recalculate_user_total_spent(db, int(order.user_id))
        db.add(order)
        db.commit()
        db.refresh(order)

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id.asc()).all()
    return ResponseModel(data=_serialize_order_detail(order, items))


@router.post(
    "/orders/{order_no}/refund-trace",
    response_model=ResponseModel[AdminRefundTraceOut],
    include_in_schema=False,
)
async def trace_order_refund(
    order_no: str,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_no == order_no).with_for_update().first()
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    if not is_wechat_pay_real_mode():
        return ResponseModel(data=_build_refund_trace_out(order, trade_state="MOCK"))

    try:
        trade = await query_trade_state(order.order_no)
    except WechatPayConfigError as exc:
        return ResponseModel(code=400, message=str(exc), data=None)
    except WechatPayRequestError as exc:
        return ResponseModel(code=502, message=str(exc), data=None)
    except WechatPayError as exc:
        return ResponseModel(code=500, message=str(exc), data=None)

    validation_error = _validate_wechat_trade_for_order(order, trade)
    if validation_error:
        return ResponseModel(code=400, message=validation_error, data=None)

    apply_wechat_trade_trace(db, order, trade)
    db.commit()
    db.refresh(order)

    return ResponseModel(
        data=_build_refund_trace_out(
            order,
            trade_state=trade.trade_state,
            trade_state_desc=trade.trade_state_desc,
            transaction_id=trade.transaction_id,
        )
    )


@router.post(
    "/orders/refund-traces",
    response_model=ResponseModel[list[AdminRefundTraceOut]],
    include_in_schema=False,
)
async def trace_recent_order_refunds(
    delivery_date: date | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Order)
        .filter(Order.paid_at.isnot(None), Order.status.in_(REFUND_TRACE_ORDER_STATUSES))
    )
    if delivery_date:
        query = query.filter(Order.delivery_date == delivery_date)

    orders = query.order_by(Order.created_at.desc()).limit(limit).all()
    if not is_wechat_pay_real_mode():
        return ResponseModel(data=[_build_refund_trace_out(order, trade_state="MOCK") for order in orders])

    results: list[AdminRefundTraceOut] = []
    for order in orders:
        try:
            trade = await query_trade_state(order.order_no)
        except (WechatPayConfigError, WechatPayRequestError, WechatPayError) as exc:
            results.append(_build_refund_trace_out(order, trade_state="ERROR", error_message=str(exc)))
            continue

        validation_error = _validate_wechat_trade_for_order(order, trade)
        if validation_error:
            results.append(_build_refund_trace_out(order, trade_state="ERROR", error_message=validation_error))
            continue

        apply_wechat_trade_trace(db, order, trade)
        db.flush()
        results.append(
            _build_refund_trace_out(
                order,
                trade_state=trade.trade_state,
                trade_state_desc=trade.trade_state_desc,
                transaction_id=trade.transaction_id,
            )
        )

    db.commit()
    return ResponseModel(data=results)
