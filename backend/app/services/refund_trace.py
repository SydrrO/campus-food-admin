from sqlalchemy.orm import Session

from app.models import Order, OrderStatus
from app.services.membership import recalculate_user_total_spent, reverse_order_spend
from app.services.wechat_pay import WechatPayTradeState
from app.utils.timezone import now_china


WECHAT_REFUND_TRADE_STATE = "REFUND"


def apply_wechat_trade_trace(db: Session, order: Order, trade: WechatPayTradeState) -> bool:
    checked_at = now_china()

    order.wechat_trade_state = trade.trade_state or None
    order.wechat_trade_state_desc = trade.trade_state_desc or None
    order.refund_checked_at = checked_at
    if trade.transaction_id and not order.transaction_id:
        order.transaction_id = trade.transaction_id

    became_refunded = False
    if trade.trade_state == WECHAT_REFUND_TRADE_STATE:
        became_refunded = order.status != OrderStatus.refunded
        reverse_order_spend(db, order)
        order.status = OrderStatus.refunded
        order.refunded_at = order.refunded_at or checked_at
        recalculate_user_total_spent(db, int(order.user_id))

    db.add(order)
    return became_refunded
