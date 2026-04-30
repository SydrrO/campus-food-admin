from sqlalchemy import Column, Integer, String, TIMESTAMP, Boolean, Enum
import enum

from app.db.base import Base
from app.utils.timezone import now_china


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    real_name = Column(String(50))
    role = Column(Enum(AdminRole), default=AdminRole.admin, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
