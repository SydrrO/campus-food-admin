from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import Admin
from app.schemas.admin import AdminLoginIn, AdminLoginOut, AdminOut
from app.schemas.response import ResponseModel


router = APIRouter()


def _serialize_admin(admin: Admin) -> AdminOut:
    return AdminOut(
        id=int(admin.id),
        username=admin.username,
        real_name=admin.real_name,
        role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
        is_active=bool(admin.is_active),
    )


@router.post("/login", response_model=ResponseModel[AdminLoginOut])
async def login(payload: AdminLoginIn, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == payload.username, Admin.is_active == True).first()
    if not admin or not verify_password(payload.password, admin.password):
        return ResponseModel(code=401, message="Invalid username or password", data=None)

    token = create_access_token(user_id=int(admin.id), role="admin")
    return ResponseModel(
        data=AdminLoginOut(
            token=token,
            admin=_serialize_admin(admin),
        )
    )


@router.get("/me", response_model=ResponseModel[AdminOut])
async def get_me(current_admin: Admin = Depends(get_current_admin)):
    return ResponseModel(data=_serialize_admin(current_admin))
