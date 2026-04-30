from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.schemas.order import OrderItemOut


class AdminOrderSummaryOut(BaseModel):
    order_id: int
    order_no: str
    user_id: int
    status: str
    meal_type: str
    delivery_date: date
    total_amount: str
    delivery_fee: str
    actual_amount: str
    item_summary: Optional[str] = None
    item_count: int = 0
    contact_name: str
    contact_phone: str
    delivery_address: str
    remark: Optional[str] = None
    wechat_trade_state: Optional[str] = None
    refund_checked_at: Optional[str] = None
    refunded_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminOrderDetailOut(AdminOrderSummaryOut):
    pay_method: Optional[str] = None
    transaction_id: Optional[str] = None
    paid_at: Optional[str] = None
    closed_at: Optional[str] = None
    wechat_trade_state_desc: Optional[str] = None
    courier_id: Optional[int] = None
    delivered_at: Optional[str] = None
    record_text: str
    items: list[OrderItemOut]


class AdminRefundTraceOut(BaseModel):
    order_no: str
    order_status: str
    trade_state: str
    trade_state_desc: Optional[str] = None
    transaction_id: Optional[str] = None
    refund_checked_at: Optional[str] = None
    refunded_at: Optional[str] = None
    mode: str
    error_message: Optional[str] = None


class OrderStatisticsOut(BaseModel):
    date: date
    total_orders: int
    confirmed_orders: int
    completed_orders: int
    total_amount: str


class CountBreakdownOut(BaseModel):
    key: str
    label: str
    count: int


class AdminOrderMonitorOut(BaseModel):
    items: list[AdminOrderSummaryOut]
    total: int
    page: int
    page_size: int
    status_counts: list[CountBreakdownOut]
    last_updated_at: str


class OperationsTrendPointOut(BaseModel):
    date: date
    order_count: int
    revenue: str
    new_users: int


class AdminOperationsOverviewOut(BaseModel):
    snapshot_date: date
    total_users: int
    new_users_today: int
    total_orders_today: int
    paid_orders_today: int
    unpaid_orders_today: int
    active_orders_today: int
    completed_orders_today: int
    closed_orders_today: int
    today_revenue: str
    seven_day_orders: int
    seven_day_revenue: str
    category_count: int
    active_category_count: int
    dish_count: int
    active_dish_count: int
    sold_out_dish_count: int
    payment_mode: str
    app_env: str
    admin_entry: str
    api_base_url: str
    lunch_deadline: str
    dinner_deadline: str
    payment_timeout: str
    base_delivery_fee: str
    status_counts: list[CountBreakdownOut]
    meal_type_counts: list[CountBreakdownOut]
    seven_day_trend: list[OperationsTrendPointOut]
    recent_orders: list[AdminOrderSummaryOut]
