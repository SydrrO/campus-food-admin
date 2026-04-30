from sqlalchemy import Column, BigInteger, Integer, String, TIMESTAMP, Boolean, ForeignKey, JSON

from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")


class DishFlavor(Base):
    __tablename__ = "dish_flavors"

    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    dish_id = Column(SQLiteBigInt, ForeignKey("dishes.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    options = Column(JSON, nullable=False)
    is_required = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=now_china)
