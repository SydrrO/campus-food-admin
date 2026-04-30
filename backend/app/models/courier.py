from sqlalchemy import Column, BigInteger, Integer, String, TIMESTAMP, Boolean

from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")


class Courier(Base):
    __tablename__ = "couriers"

    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(11), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
