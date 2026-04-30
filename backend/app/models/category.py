from sqlalchemy import Column, Integer, String, TIMESTAMP, Boolean
from app.db.base import Base
from app.utils.timezone import now_china

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
