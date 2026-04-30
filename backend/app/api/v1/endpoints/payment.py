from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, OrderStatus, User, UserCoupon
from app.schemas.payment import (
    PaymentNotifyIn,
    PaymentNotifyOut,
    PaymentPrepayIn,
    PaymentPrepayOut,
    PaymentReconcileIn,
    PaymentReconcileOut,
)
from app.schemas.response import ResponseModel
from app.services.membership import record_order_spend
from app.services.order_lifecycle import close_order, get_config_map, get_payment_timeout_minutes, is_order_expired
from app.services.refund_trace import WECHAT_REFUND_TRADE_STATE, apply_wechat_trade_trace
from app.services.redis_timeout import clear_order_timeout, get_redis_client
from app.services.wechat_pay import (
    WechatPayConfigError,
    WechatPayError,
    WechatPayRequestError,
    _amount_to_fen,
    create_prepay,
    get_wechat_pay_mode,
    is_wechat_pay_real_mode,
    parse_wechat_pay_notification,
    query_trade_state,
)
from app.core.config import settings
from app.utils.timezone import now_china, to_china_naive


router = APIRouter()


def _clear_timeout(order_no: str) -> None:
    try:
        clear_order_timeout(get_redis_client(), order_no)
    except RedisError:
        pass


def _as_naive_datetime(value: datetime | None) -> datetime | None:
    return to_china_naive(value)


def _close_expired_unpaid_order(db: Session, order: Order, timeout_minutes: int) -> bool:
    if order.status != OrderStatus.unpaid or not is_order_expired(order, timeout_minutes):
        return False
    close_order(db, order)
    db.commit()
    db.refresh(order)
    _clear_timeout(order.order_no)
    return True


def _mark_order_paid(
    order: Order, transaction_id: str, paid_at: datetime | None, db: Session
) -> tuple[bool, str | None]:
    if not transaction_id:
        return False, "Payment transaction id missing"

    existing_transaction = (
        db.query(Order)
        .filter(Order.transaction_id == transaction_id, Order.id != order.id)
        .first()
    )
    if existing_transaction:
        return False, "Transaction already belongs to another order"

    if (
        order.transaction_id == transaction_id
        and order.status in {OrderStatus.confirmed, OrderStatus.delivering, OrderStatus.completed}
    ):
        record_order_spend(db, order)
        db.commit()
        db.refresh(order)
        return True, None
    if order.status != OrderStatus.unpaid:
        return False, "Order status does not allow payment confirmation"
    if order.transaction_id and order.transaction_id != transaction_id:
        return False, "Order already has another transaction"

    timeout_minutes = get_payment_timeout_minutes(get_config_map(db))
    if is_order_expired(order, timeout_minutes, now=_as_naive_datetime(paid_at)):
        close_order(db, order)
        db.commit()
        db.refresh(order)
        _clear_timeout(order.order_no)
        return False, "Order payment window has expired"

    order.status = OrderStatus.confirmed
    order.closed_at = None
    order.pay_method = "wechat"
    order.transaction_id = transaction_id
    order.paid_at = _as_naive_datetime(paid_at) or order.paid_at or now_china()
    record_order_spend(db, order)
    if order.coupon_id:
        coupon = db.query(UserCoupon).filter(UserCoupon.id == order.coupon_id).first()
        if coupon and coupon.status in {"reserved", "available"}:
            coupon.status = "used"
            coupon.used_at = now_china()
            coupon.locked_order_id = order.id
            db.add(coupon)
    db.add(order)
    db.commit()
    db.refresh(order)
    _clear_timeout(order.order_no)
    return True, None


@router.post("/prepay", response_model=ResponseModel[PaymentPrepayOut])
async def prepay(
    payload: PaymentPrepayIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.order_no == payload.order_no, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)
    timeout_minutes = get_payment_timeout_minutes(get_config_map(db))
    if _close_expired_unpaid_order(db, order, timeout_minutes):
        return ResponseModel(code=400, message="订单已超过15分钟支付时间，已自动关闭", data=None)
    if order.status != OrderStatus.unpaid:
        if order.actual_amount is not None and order.actual_amount <= 0 and order.status == OrderStatus.confirmed:
            return ResponseModel(
                message="订单已通过优惠抵扣完成，无需微信支付",
                data=PaymentPrepayOut(
                    timeStamp="",
                    nonceStr="",
                    package=f"prepay_id=free_{order.order_no}",
                    signType="NONE",
                    paySign="",
                    mode="free",
                ),
            )
        return ResponseModel(code=400, message="Only unpaid orders can start payment", data=None)

    try:
        pay_data = await create_prepay(order, current_user.openid)
    except WechatPayConfigError as exc:
        return ResponseModel(code=400, message=str(exc), data=None)
    except WechatPayRequestError as exc:
        return ResponseModel(code=502, message=str(exc), data=None)
    except WechatPayError as exc:
        return ResponseModel(code=500, message=str(exc), data=None)

    return ResponseModel(data=PaymentPrepayOut(**pay_data))


@router.post("/reconcile", response_model=ResponseModel[PaymentReconcileOut])
async def reconcile_payment(
    payload: PaymentReconcileIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.order_no == payload.order_no, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    if not is_wechat_pay_real_mode():
        return ResponseModel(
            data=PaymentReconcileOut(
                order_no=order.order_no,
                order_status=order.status.value,
                trade_state="MOCK",
                trade_state_desc=None,
                transaction_id=order.transaction_id,
                refund_checked_at=order.refund_checked_at.isoformat() if order.refund_checked_at else None,
                refunded_at=order.refunded_at.isoformat() if order.refunded_at else None,
                mode=get_wechat_pay_mode(),
            )
        )

    try:
        trade = await query_trade_state(order.order_no)
    except WechatPayConfigError as exc:
        return ResponseModel(code=400, message=str(exc), data=None)
    except WechatPayRequestError as exc:
        return ResponseModel(code=502, message=str(exc), data=None)
    except WechatPayError as exc:
        return ResponseModel(code=500, message=str(exc), data=None)

    if trade.appid != settings.WECHAT_APPID:
        return ResponseModel(code=400, message="AppID mismatch", data=None)
    if trade.mchid != settings.WECHAT_MCHID:
        return ResponseModel(code=400, message="MchID mismatch", data=None)
    if trade.currency != "CNY":
        return ResponseModel(code=400, message="Currency mismatch", data=None)
    if trade.amount_total != _amount_to_fen(order.actual_amount):
        return ResponseModel(code=400, message="Amount mismatch", data=None)
    if trade.payer_openid and trade.payer_openid != current_user.openid:
        return ResponseModel(code=400, message="Payer openid mismatch", data=None)

    if trade.trade_state == "SUCCESS":
        success, error = _mark_order_paid(order, trade.transaction_id or "", trade.paid_at, db)
        if not success:
            return ResponseModel(code=400, message=error or "Payment reconcile failed", data=None)
    elif trade.trade_state == WECHAT_REFUND_TRADE_STATE:
        apply_wechat_trade_trace(db, order, trade)
        db.commit()

    db.refresh(order)
    return ResponseModel(
        data=PaymentReconcileOut(
            order_no=order.order_no,
            order_status=order.status.value,
            trade_state=trade.trade_state,
            trade_state_desc=trade.trade_state_desc,
            transaction_id=trade.transaction_id,
            refund_checked_at=order.refund_checked_at.isoformat() if order.refund_checked_at else None,
            refunded_at=order.refunded_at.isoformat() if order.refunded_at else None,
            mode=get_wechat_pay_mode(),
        )
    )


@router.post("/notify/mock", response_model=ResponseModel[PaymentNotifyOut])
async def payment_notify_mock(payload: PaymentNotifyIn, db: Session = Depends(get_db)):
    if is_wechat_pay_real_mode():
        return ResponseModel(
            code=400,
            message="当前为真实微信支付模式，请使用 /api/v1/payment/notify",
            data=None,
        )
    order = (
        db.query(Order)
        .filter(Order.order_no == payload.order_no)
        .with_for_update()
        .first()
    )
    if not order:
        return ResponseModel(code=404, message="Order not found", data=None)

    success, error = _mark_order_paid(order, payload.transaction_id, payload.pay_time, db)
    if not success:
        return ResponseModel(code=400, message=error or "Payment notify failed", data=None)

    return ResponseModel(
        data=PaymentNotifyOut(
            order_no=order.order_no,
            status=order.status.value,
            transaction_id=order.transaction_id or payload.transaction_id,
            mode=get_wechat_pay_mode(),
        )
    )


@router.post("/notify")
async def payment_notify(request: Request, db: Session = Depends(get_db)):
    if not is_wechat_pay_real_mode():
        return JSONResponse(
            status_code=400,
            content={"code": "FAIL", "message": "当前为 mock 模式，请使用 /api/v1/payment/notify/mock"},
        )

    body = await request.body()
    try:
        notification = parse_wechat_pay_notification(request.headers, body)
    except WechatPayError as exc:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": str(exc)})

    order = (
        db.query(Order)
        .filter(Order.order_no == notification.order_no)
        .with_for_update()
        .first()
    )
    if not order:
        return JSONResponse(status_code=404, content={"code": "FAIL", "message": "Order not found"})

    user = db.query(User).filter(User.id == order.user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"code": "FAIL", "message": "User not found"})

    if notification.appid != settings.WECHAT_APPID:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "AppID mismatch"})
    if notification.mchid != settings.WECHAT_MCHID:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "MchID mismatch"})
    if notification.currency != "CNY":
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Currency mismatch"})
    if notification.amount_total != _amount_to_fen(order.actual_amount):
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Amount mismatch"})
    if not notification.payer_openid:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Payer openid missing"})
    if notification.payer_openid != user.openid:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "Payer openid mismatch"})

    success, error = _mark_order_paid(
        order, notification.transaction_id, notification.paid_at, db
    )
    if not success:
        return JSONResponse(
            status_code=400,
            content={"code": "FAIL", "message": error or "Payment notify failed"},
        )
    return JSONResponse(status_code=200, content={"code": "SUCCESS", "message": "成功"})
