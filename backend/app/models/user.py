from sqlalchemy import Boolean, Column, BigInteger, Integer, String, TIMESTAMP, DECIMAL
from app.db.base import Base
from app.utils.timezone import now_china

SQLiteBigInt = BigInteger().with_variant(Integer, "sqlite")

class User(Base):
    __tablename__ = "users"
    
    id = Column(SQLiteBigInt, primary_key=True, autoincrement=True)
    openid = Column(String(64), unique=True, nullable=False, index=True)
    public_uid = Column(String(32), unique=True, nullable=True, index=True)
    nickname = Column(String(100))
    avatar_url = Column(String(255))
    phone = Column(String(11))
    is_registered = Column(Boolean, default=False, nullable=False, index=True)
    is_member = Column(Boolean, default=False, nullable=False, index=True)
    invite_code = Column(String(5), unique=True, nullable=True, index=True)
    invited_by_user_id = Column(SQLiteBigInt, nullable=True, index=True)
    points = Column(Integer, default=0, nullable=False)
    total_spent = Column(DECIMAL(10, 2), default=0, nullable=False)
    registered_at = Column(TIMESTAMP, nullable=True)
    member_joined_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=now_china)
    updated_at = Column(TIMESTAMP, default=now_china, onupdate=now_china)
