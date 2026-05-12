from sqlalchemy import Column, Integer, String, TIMESTAMP
from app.db.base import Base
from app.utils.timezone import now_china

class SystemConfig(Base):
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(50), unique=True, nullable=False)
    config_value = Column(String(500), nullable=False)
    description = Column(String(200))
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
