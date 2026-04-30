from sqlalchemy import Column, BigInteger, Integer, String, Text, DECIMAL, Boolean, TIMESTAMP, ForeignKey
from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")

class Dish(Base):
    __tablename__ = "dishes"
    
    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    detail_content = Column(Text)
    image_url = Column(String(255))
    price = Column(DECIMAL(10, 2), nullable=False)
    stock = Column(Integer, default=-1)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_sold_out = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
