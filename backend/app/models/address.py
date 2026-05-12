from sqlalchemy import Column, BigInteger, Integer, String, TIMESTAMP, Boolean, ForeignKey

from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    user_id = Column(SQLiteBigInt, ForeignKey("users.id"), nullable=False, index=True)
    contact_name = Column(String(50), nullable=False)
    contact_phone = Column(String(11), nullable=False)
    building = Column(String(50), nullable=False)
    room_number = Column(String(20))
    detail_address = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
