from sqlalchemy import Column, BigInteger, String, TIMESTAMP, ForeignKey, Integer, DECIMAL, JSON

from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    order_id = Column(SQLiteBigInt, ForeignKey("orders.id"), nullable=False, index=True)
    dish_id = Column(SQLiteBigInt, nullable=False)
    dish_name = Column(String(100), nullable=False)
    dish_image = Column(String(255))
    price = Column(DECIMAL(10, 2), nullable=False)
    cost_price = Column(DECIMAL(10, 2), nullable=False, default=0)
    quantity = Column(Integer, nullable=False)
    flavors = Column(JSON)
    subtotal = Column(DECIMAL(10, 2), nullable=False)
    created_at = Column(TIMESTAMP, default=now_china)
