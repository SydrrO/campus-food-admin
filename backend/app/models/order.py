from sqlalchemy import Column, BigInteger, Integer, String, Date, DECIMAL, Enum, TIMESTAMP, ForeignKey
from app.db.base import Base
from app.utils.timezone import now_china
import enum

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")

class MealType(str, enum.Enum):
    lunch = "lunch"
    dinner = "dinner"

class OrderStatus(str, enum.Enum):
    unpaid = "unpaid"
    closed = "closed"
    confirmed = "confirmed"
    delivering = "delivering"
    completed = "completed"
    refunded = "refunded"

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    order_no = Column(String(32), unique=True, nullable=False, index=True)
    user_id = Column(SQLiteBigInt, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(64), nullable=True, index=True)
    contact_name = Column(String(50), nullable=False)
    contact_phone = Column(String(11), nullable=False)
    delivery_address = Column(String(500), nullable=False)
    meal_type = Column(Enum(MealType), nullable=False)
    delivery_date = Column(Date, nullable=False, index=True)
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    delivery_fee = Column(DECIMAL(10, 2), default=0)
    discount_amount = Column(DECIMAL(10, 2), default=0)
    actual_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.unpaid, index=True)
    remark = Column(String(500))
    coupon_id = Column(SQLiteBigInt, nullable=True, index=True)
    pay_method = Column(String(20))
    transaction_id = Column(String(64), unique=True, nullable=True, index=True)
    paid_at = Column(TIMESTAMP, nullable=True)
    spend_counted_at = Column(TIMESTAMP, nullable=True)
    wechat_trade_state = Column(String(32), nullable=True, index=True)
    wechat_trade_state_desc = Column(String(256), nullable=True)
    refund_checked_at = Column(TIMESTAMP, nullable=True)
    refunded_at = Column(TIMESTAMP, nullable=True)
    courier_id = Column(SQLiteBigInt, nullable=True)
    delivered_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=now_china, index=True)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
    closed_at = Column(TIMESTAMP, nullable=True)
