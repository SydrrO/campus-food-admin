from sqlalchemy import Column, BigInteger, Integer, String, DECIMAL, TIMESTAMP, ForeignKey

from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")


class UserCoupon(Base):
    __tablename__ = "user_coupons"

    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    user_id = Column(SQLiteBigInt, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(50), default="随机立减券", nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=True)
    status = Column(String(20), default="unrevealed", nullable=False, index=True)
    created_at = Column(TIMESTAMP, default=now_china)
    revealed_at = Column(TIMESTAMP, nullable=True)
    used_at = Column(TIMESTAMP, nullable=True)
    locked_order_id = Column(SQLiteBigInt, nullable=True, index=True)
