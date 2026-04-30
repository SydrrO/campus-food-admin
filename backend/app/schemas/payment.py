from datetime import datetime

from pydantic import BaseModel


class PaymentPrepayIn(BaseModel):
    order_no: str


class PaymentPrepayOut(BaseModel):
    timeStamp: str
    nonceStr: str
    package: str
    signType: str
    paySign: str
    mode: str = "mock"


class PaymentNotifyIn(BaseModel):
    order_no: str
    transaction_id: str
    pay_time: datetime | None = None


class PaymentNotifyOut(BaseModel):
    order_no: str
    status: str
    transaction_id: str
    mode: str = "mock"


class PaymentReconcileIn(BaseModel):
    order_no: str


class PaymentReconcileOut(BaseModel):
    order_no: str
    order_status: str
    trade_state: str
    trade_state_desc: str | None = None
    transaction_id: str | None = None
    refund_checked_at: str | None = None
    refunded_at: str | None = None
    mode: str = "mock"


class WechatPayNotifyAck(BaseModel):
    code: str
    message: str
