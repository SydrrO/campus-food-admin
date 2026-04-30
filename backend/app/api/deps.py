from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Admin, User


bearer_scheme = HTTPBearer(auto_error=True)

UNREGISTERED_ALLOWED_PATH_SUFFIXES = (
    "/v1/users/me",
    "/v1/users/profile",
    "/v1/users/avatar",
    "/v1/users/register",
)


def _allows_unregistered_user(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in UNREGISTERED_ALLOWED_PATH_SUFFIXES)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET or "dev-jwt-secret",
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from error

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or role != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_registered and not _allows_unregistered_user(request.url.path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先创建账号")

    return user


def get_current_registered_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_registered:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先创建账号",
        )
    return current_user


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET or "dev-jwt-secret",
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from error

    admin_id = payload.get("sub")
    role = payload.get("role")
    if not admin_id or role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    admin = db.query(Admin).filter(Admin.id == int(admin_id), Admin.is_active == True).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")

    return admin
