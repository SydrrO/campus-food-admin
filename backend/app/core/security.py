from datetime import datetime, timedelta, timezone
from hashlib import sha256

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def create_access_token(user_id: int, role: str = "user") -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET or "dev-jwt-secret", algorithm=settings.JWT_ALGORITHM)


def build_mock_openid(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()[:32]


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
