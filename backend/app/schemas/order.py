from pydantic import BaseModel
from datetime import date
from typing import Optional, List

class OrderItemIn(BaseModel):
    dish_id: int
    quantity: int
    flavors: Optional[dict] = None

class OrderCreateIn(BaseModel):
    address_id: int
    meal_type: str
    delivery_date: date
    items: List[OrderItemIn]
    remark: Optional[str] = None
    coupon_id: Optional[int] = None
    idempotency_key: Optional[str] = None

class OrderCreateOut(BaseModel):
    order_id: int
    order_no: str
    status: str = "unpaid"
    total_amount: str
    delivery_fee: str
    discount_amount: str = "0.00"
    actual_amount: str
    expire_time: Optional[str] = None


class OrderItemOut(BaseModel):
    dish_id: int
    dish_name: str
    dish_image: Optional[str] = None
    price: str
    quantity: int
    flavors: Optional[dict] = None
    subtotal: str

    class Config:
        from_attributes = True


class OrderSummaryOut(BaseModel):
    order_id: int
    order_no: str
    status: str
    meal_type: str
    delivery_date: date
    total_amount: str
    delivery_fee: str
    discount_amount: str = "0.00"
    coupon_id: Optional[int] = None
    actual_amount: str
    contact_name: str
    contact_phone: str
    delivery_address: str
    remark: Optional[str] = None
    created_at: Optional[str] = None
    expire_time: Optional[str] = None
    items: List[OrderItemOut] = []


class OrderDetailOut(OrderSummaryOut):
    pass
