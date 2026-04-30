import random
import string

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import build_mock_openid, create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserLoginIn, LoginOut, UserOut
from app.schemas.response import ResponseModel
from app.services.membership import build_membership_state
from app.services.wechat_pay import is_wechat_pay_real_mode
from app.services.wechat_auth import (
    WechatAuthConfigError,
    WechatAuthRequestError,
    exchange_code_for_openid,
)

router = APIRouter()


def _generate_public_uid(db: Session) -> str:
    for _ in range(20):
        value = "SD" + "".join(random.choices(string.ascii_uppercase + string.digits, k=14))
        if not db.query(User.id).filter(User.public_uid == value).first():
            return value
    raise RuntimeError("Failed to generate user uid")


def _display_id(public_uid: str | None) -> str:
    if not public_uid:
        return "ID 待生成"
    if len(public_uid) <= 10:
        return public_uid
    return f"{public_uid[:4]}...{public_uid[-4:]}"


def _is_default_nickname(nickname: str | None) -> bool:
    value = (nickname or "").strip()
    return not value or value.startswith("微信用户")


def _serialize_user(db: Session, user: User) -> UserOut:
    membership_state = build_membership_state(db, user)
    return UserOut(
        id=int(user.id),
        display_id=_display_id(user.public_uid),
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        phone=user.phone,
        is_registered=bool(user.is_registered),
        is_member=bool(user.is_member),
        invite_code=user.invite_code,
        points=user.points or 0,
        **membership_state,
    )

@router.post("/login", response_model=ResponseModel[LoginOut])
async def login(payload: UserLoginIn, db: Session = Depends(get_db)):
    """微信登录：mock 模式下生成测试 openid，real 模式下调用 code2session。"""
    try:
        if is_wechat_pay_real_mode():
            openid = await exchange_code_for_openid(payload.code)
        else:
            openid = build_mock_openid(payload.code)
    except WechatAuthConfigError as exc:
        return ResponseModel(code=400, message=str(exc), data=None)
    except WechatAuthRequestError as exc:
        return ResponseModel(code=502, message=str(exc), data=None)

    user = db.query(User).filter(User.openid == openid).first()
    is_new_user = False

    if not user:
        user = User(openid=openid, nickname=f"微信用户{openid[-6:]}", is_registered=False)
        db.add(user)
        db.commit()
        db.refresh(user)
        is_new_user = True
    elif not user.is_registered and user.public_uid and _is_default_nickname(user.nickname):
        user.public_uid = None
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user_id=int(user.id), role="user")
    return ResponseModel(data=LoginOut(token=token, user=_serialize_user(db, user), is_new_user=is_new_user))
