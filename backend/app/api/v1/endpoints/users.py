import random
import shutil
import string
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import Address, User, UserCoupon
from app.schemas.response import ResponseModel
from app.schemas.user import (
    AddressCreateIn,
    AddressOut,
    AddressUpdateIn,
    CouponRedeemIn,
    CouponRedeemOut,
    CouponRedemptionOptionOut,
    CouponOut,
    MemberOut,
    MemberRegisterIn,
    UserProfileOut,
    UserRegisterIn,
    UserProfileUpdateIn,
)
from app.services.membership import build_membership_state
from app.utils.timezone import now_china


router = APIRouter()

DEFAULT_UPLOADS_DIR = Path(__file__).resolve().parents[4] / "uploads"
ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

ALLOWED_ADDRESS_BUILDINGS = {"男寝", "女寝", "书4", "书5", "男9", "女9", "男7", "东区"}
INVITE_REWARD_POINTS = 30
INVITE_CODE_ALPHABET = string.ascii_letters + string.digits
COUPON_REDEMPTION_OPTIONS = {
    "coupon_010": {
        "title": "0.1元积分兑换券",
        "amount": Decimal("0.10"),
        "points_cost": 1000,
    },
    "coupon_random": {
        "title": "幸运转盘",
        "amount": Decimal("0.10"),
        "points_cost": 3000,
    },
    "coupon_050": {
        "title": "0.5元积分兑换券",
        "amount": Decimal("0.50"),
        "points_cost": 3000,
    },
    "coupon_100": {
        "title": "1元积分兑换券",
        "amount": Decimal("1.00"),
        "points_cost": 6000,
    },
    "coupon_200": {
        "title": "2元积分兑换券",
        "amount": Decimal("2.00"),
        "points_cost": 10000,
    },
}


def _clear_default_addresses(db: Session, user_id: int, exclude_id: int | None = None) -> None:
    query = db.query(Address).filter(Address.user_id == user_id, Address.is_default.is_(True))
    if exclude_id is not None:
        query = query.filter(Address.id != exclude_id)
    query.update({Address.is_default: False}, synchronize_session=False)


def _validate_address_building(building: str) -> ResponseModel | None:
    if building not in ALLOWED_ADDRESS_BUILDINGS:
        return ResponseModel(code=400, message="配送区域暂不支持，请重新选择", data=None)
    return None


def _generate_public_uid(db: Session) -> str:
    for _ in range(20):
        value = "SD" + "".join(random.choices(string.ascii_uppercase + string.digits, k=14))
        if not db.query(User.id).filter(User.public_uid == value).first():
            return value
    raise RuntimeError("Failed to generate user uid")


def _generate_invite_code(db: Session) -> str:
    for _ in range(50):
        value = "".join(random.choices(INVITE_CODE_ALPHABET, k=5))
        if not db.query(User.id).filter(User.invite_code == value).first():
            return value
    raise RuntimeError("Failed to generate invite code")


def _ensure_user_public_uid(db: Session, user: User) -> None:
    if user.public_uid:
        return
    user.public_uid = _generate_public_uid(db)
    db.add(user)


def _is_default_nickname(nickname: str | None) -> bool:
    value = (nickname or "").strip()
    return not value or value.startswith("微信用户")


def _mark_registered_if_ready(db: Session, user: User) -> bool:
    if _is_default_nickname(user.nickname):
        return False
    if not user.public_uid:
        user.public_uid = _generate_public_uid(db)
    if not user.is_registered:
        user.is_registered = True
        user.registered_at = now_china()
    db.add(user)
    return True


def _ensure_member_coupon(db: Session, user_id: int) -> None:
    existing = db.query(UserCoupon.id).filter(UserCoupon.user_id == user_id).first()
    if existing:
        return
    db.add(UserCoupon(user_id=user_id, title="随机立减券", status="unrevealed"))


def reveal_coupon_for_order(db: Session, coupon: UserCoupon) -> UserCoupon:
    if coupon.status == "unrevealed":
        coupon.status = "available"
        coupon.title = "0.5元券"
        coupon.amount = Decimal("0.50")
        coupon.revealed_at = now_china()
        db.add(coupon)
    return coupon


def _serialize_coupon(coupon: UserCoupon) -> CouponOut:
    if coupon.status == "unrevealed" or coupon.amount is None:
        display_title = "随机立减券"
    else:
        amount_text = format(Decimal(str(coupon.amount)).quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
        display_title = f"{amount_text}元券"
    return CouponOut(
        id=int(coupon.id),
        title=coupon.title,
        amount=str(coupon.amount) if coupon.amount is not None else None,
        status=coupon.status,
        display_title=display_title,
    )


def _serialize_redemption_option(option_id: str, option: dict, user_points: int) -> CouponRedemptionOptionOut:
    points_cost = int(option["points_cost"])
    amount = Decimal(str(option["amount"])).quantize(Decimal("0.01"))
    return CouponRedemptionOptionOut(
        id=option_id,
        title=str(option["title"]),
        amount=str(amount),
        points_cost=points_cost,
        user_points=user_points,
        can_redeem=user_points >= points_cost,
    )


def _display_id(public_uid: str | None) -> str:
    if not public_uid:
        return "ID 待生成"
    if len(public_uid) <= 10:
        return public_uid
    return f"{public_uid[:4]}...{public_uid[-4:]}"


def _serialize_profile(db: Session, user: User) -> UserProfileOut:
    membership_state = build_membership_state(db, user)
    return UserProfileOut(
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


def _serialize_membership(db: Session, user: User) -> MemberOut:
    membership_state = build_membership_state(db, user)
    return MemberOut(
        is_member=bool(user.is_member),
        invite_code=user.invite_code,
        points=user.points or 0,
        invite_reward_points=INVITE_REWARD_POINTS,
        **membership_state,
    )


def _get_uploads_dir() -> Path:
    if settings.UPLOADS_ROOT:
        return Path(settings.UPLOADS_ROOT).resolve()
    return DEFAULT_UPLOADS_DIR


def _get_uploads_public_path() -> str:
    public_path = settings.UPLOADS_PUBLIC_PATH or "/uploads"
    return public_path if public_path.startswith("/") else f"/{public_path}"


def _build_avatar_url(request: Request, filename: str) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    scheme = (forwarded_proto.split(",")[0].strip() if forwarded_proto else request.url.scheme)
    host = (forwarded_host.split(",")[0].strip() if forwarded_host else request.headers.get("host"))
    return f"{scheme}://{host}{_get_uploads_public_path()}/avatars/{filename}"


@router.get("/me", response_model=ResponseModel[UserProfileOut])
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户信息。"""
    return ResponseModel(data=_serialize_profile(db, current_user))


@router.put("/profile", response_model=ResponseModel[UserProfileOut])
async def update_profile(
    payload: UserProfileUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新用户资料。"""
    if payload.nickname is not None:
        current_user.nickname = payload.nickname
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    _mark_registered_if_ready(db, current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return ResponseModel(data=_serialize_profile(db, current_user))


@router.put("/me", response_model=ResponseModel[UserProfileOut])
async def update_me(
    payload: UserProfileUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧前端路径的用户资料更新接口。"""
    return await update_profile(payload, current_user, db)


@router.post("/register", response_model=ResponseModel[UserProfileOut])
async def register_account(
    payload: UserRegisterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nickname = (payload.nickname or "").strip()
    if _is_default_nickname(nickname):
        return ResponseModel(code=400, message="请填写微信昵称后创建账号", data=None)

    current_user.nickname = nickname
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    _mark_registered_if_ready(db, current_user)
    db.commit()
    db.refresh(current_user)
    return ResponseModel(data=_serialize_profile(db, current_user))


@router.post("/avatar", response_model=ResponseModel[dict[str, str]])
async def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suffix = Path(avatar.filename or "").suffix.lower()
    if suffix not in ALLOWED_AVATAR_EXTENSIONS:
        suffix = ".jpg"

    avatar_upload_dir = _get_uploads_dir() / "avatars"
    avatar_upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"user_{int(current_user.id)}_{uuid.uuid4().hex}{suffix}"
    target_path = avatar_upload_dir / filename

    with target_path.open("wb") as output:
        shutil.copyfileobj(avatar.file, output)

    avatar_url = _build_avatar_url(request, filename)
    current_user.avatar_url = avatar_url
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return ResponseModel(data={"avatar_url": avatar_url})


@router.get("/membership", response_model=ResponseModel[MemberOut])
async def get_membership(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ResponseModel(data=_serialize_membership(db, current_user))


@router.post("/membership/register", response_model=ResponseModel[MemberOut])
async def register_membership(
    payload: MemberRegisterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注册会员，可填写邀请码；邀请人获得积分奖励。"""
    _ensure_user_public_uid(db, current_user)

    if not current_user.is_member:
        normalized_invite_code = (payload.invite_code or "").strip()
        inviter = None
        if normalized_invite_code:
            inviter = db.query(User).filter(User.invite_code == normalized_invite_code).first()
            if not inviter:
                return ResponseModel(code=404, message="邀请码不存在", data=None)
            if inviter.id == current_user.id:
                return ResponseModel(code=400, message="不能使用自己的邀请码", data=None)

        current_user.is_member = True
        current_user.member_joined_at = now_china()
        current_user.invite_code = current_user.invite_code or _generate_invite_code(db)
        if inviter:
            current_user.invited_by_user_id = inviter.id
            inviter.points = (inviter.points or 0) + INVITE_REWARD_POINTS
            db.add(inviter)
        _ensure_member_coupon(db, int(current_user.id))
    elif not current_user.invite_code:
        current_user.invite_code = _generate_invite_code(db)
        _ensure_member_coupon(db, int(current_user.id))

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return ResponseModel(data=_serialize_membership(db, current_user))


@router.get("/coupons", response_model=ResponseModel[list[CouponOut]])
async def list_coupons(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.is_member:
        _ensure_member_coupon(db, int(current_user.id))
        db.commit()

    coupons = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == current_user.id)
        .order_by(UserCoupon.id.desc())
        .all()
    )
    return ResponseModel(data=[_serialize_coupon(coupon) for coupon in coupons])


@router.get("/coupon-redemptions", response_model=ResponseModel[list[CouponRedemptionOptionOut]])
async def list_coupon_redemptions(
    current_user: User = Depends(get_current_user),
):
    user_points = int(current_user.points or 0)
    return ResponseModel(
        data=[
            _serialize_redemption_option(option_id, option, user_points)
            for option_id, option in COUPON_REDEMPTION_OPTIONS.items()
        ]
    )


@router.post("/coupons/redeem", response_model=ResponseModel[CouponRedeemOut])
async def redeem_coupon(
    payload: CouponRedeemIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    option = COUPON_REDEMPTION_OPTIONS.get(payload.option_id)
    if not option:
        return ResponseModel(code=404, message="兑换项不存在", data=None)

    user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
    if not user:
        return ResponseModel(code=404, message="用户不存在", data=None)

    points_cost = int(option["points_cost"])
    if int(user.points or 0) < points_cost:
        return ResponseModel(code=400, message="积分不足，暂时无法兑换", data=None)

    reward_type = None
    reward_title = None
    reward_points = None
    reward_amount = None

    if payload.option_id == "coupon_random":
        prizes = [
            ("0.1元券", Decimal("0.10"), 55, "coupon", 0),
            ("0.3元券", Decimal("0.30"), 44, "coupon", 0),
            ("5元券", Decimal("5.00"), 1, "coupon", 0),
            ("888积分", Decimal("0"), 8, "points", 888),
            ("18888积分", Decimal("0"), 1, "points", 18888),
            ("鸡腿兑换券", Decimal("0"), 8, "product_coupon", 0),
        ]
        weights = [p[2] for p in prizes]
        picked = random.choices(prizes, weights=weights, k=1)[0]
        prize_type = picked[3]
        reward_type = prize_type
        reward_title = picked[0]

        if prize_type == "points":
            reward_points = picked[4]
            user.points = int(user.points or 0) - points_cost + reward_points
            coupon = UserCoupon(
                user_id=user.id,
                title="积分奖励",
                amount=Decimal("0"),
                status="available",
                revealed_at=now_china(),
            )
        elif prize_type == "product_coupon":
            user.points = int(user.points or 0) - points_cost
            coupon = UserCoupon(
                user_id=user.id,
                title="鸡腿兑换券",
                amount=Decimal("0"),
                status="available",
                coupon_type="product",
                target_dish_name="炸鸡腿",
                target_quantity=1,
                revealed_at=now_china(),
            )
        else:
            amount = picked[1]
            reward_amount = str(amount)
            user.points = int(user.points or 0) - points_cost
            coupon = UserCoupon(
                user_id=user.id,
                title=picked[0],
                amount=amount,
                status="available",
                revealed_at=now_china(),
            )
    else:
        amount = Decimal(str(option["amount"])).quantize(Decimal("0.01"))
        user.points = int(user.points or 0) - points_cost
        coupon = UserCoupon(
            user_id=user.id,
            title=str(option["title"]),
            amount=amount,
            status="available",
            revealed_at=now_china(),
        )
    db.add(user)
    db.add(coupon)
    db.commit()
    db.refresh(user)
    db.refresh(coupon)

    return ResponseModel(
        data=CouponRedeemOut(
            coupon=_serialize_coupon(coupon),
            points=int(user.points or 0),
            reward_type=reward_type,
            reward_title=reward_title,
            reward_points=reward_points,
            reward_amount=reward_amount,
        )
    )


@router.post("/coupons/{coupon_id}/reveal", response_model=ResponseModel[CouponOut])
async def reveal_coupon(
    coupon_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    coupon = (
        db.query(UserCoupon)
        .filter(UserCoupon.id == coupon_id, UserCoupon.user_id == current_user.id)
        .first()
    )
    if not coupon:
        return ResponseModel(code=404, message="优惠券不存在", data=None)

    if coupon.status == "unrevealed":
        reveal_coupon_for_order(db, coupon)
        db.commit()
        db.refresh(coupon)

    return ResponseModel(data=_serialize_coupon(coupon))


@router.get("/addresses", response_model=ResponseModel[list[AddressOut]])
async def list_addresses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户地址列表。"""
    addresses = (
        db.query(Address)
        .filter(Address.user_id == current_user.id)
        .order_by(Address.is_default.desc(), Address.id.desc())
        .all()
    )
    return ResponseModel(data=[AddressOut.model_validate(address) for address in addresses])


@router.get("/addresses/{address_id}", response_model=ResponseModel[AddressOut])
async def get_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个地址详情。"""
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        return ResponseModel(code=404, message="Address not found", data=None)
    return ResponseModel(data=AddressOut.model_validate(address))


@router.post("/addresses", response_model=ResponseModel[AddressOut])
async def create_address(
    payload: AddressCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建地址，支持设置默认地址。"""
    building_error = _validate_address_building(payload.building)
    if building_error:
        return building_error

    if payload.is_default:
        _clear_default_addresses(db, current_user.id)

    has_any_address = db.query(Address.id).filter(Address.user_id == current_user.id).first() is not None
    address = Address(
        user_id=current_user.id,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        building=payload.building,
        room_number=payload.room_number,
        detail_address=payload.detail_address,
        is_default=payload.is_default or not has_any_address,
    )
    db.add(address)
    db.commit()
    db.refresh(address)

    return ResponseModel(data=AddressOut.model_validate(address))


@router.put("/addresses/{address_id}", response_model=ResponseModel[AddressOut])
async def update_address(
    address_id: int,
    payload: AddressUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新地址。"""
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        return ResponseModel(code=404, message="Address not found", data=None)

    building_error = _validate_address_building(payload.building)
    if building_error:
        return building_error

    if payload.is_default:
        _clear_default_addresses(db, current_user.id, exclude_id=address.id)

    address.contact_name = payload.contact_name
    address.contact_phone = payload.contact_phone
    address.building = payload.building
    address.room_number = payload.room_number
    address.detail_address = payload.detail_address
    address.is_default = payload.is_default
    db.add(address)
    db.commit()
    db.refresh(address)
    return ResponseModel(data=AddressOut.model_validate(address))


@router.delete("/addresses/{address_id}", response_model=ResponseModel[dict[str, bool]])
async def delete_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除地址。"""
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        return ResponseModel(code=404, message="Address not found", data=None)

    was_default = address.is_default
    db.delete(address)
    db.commit()

    if was_default:
        next_address = (
            db.query(Address)
            .filter(Address.user_id == current_user.id)
            .order_by(Address.id.desc())
            .first()
        )
        if next_address:
            next_address.is_default = True
            db.add(next_address)
            db.commit()

    return ResponseModel(data={"success": True})


@router.put("/addresses/{address_id}/default", response_model=ResponseModel[AddressOut])
async def set_default_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """设置默认地址。"""
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        return ResponseModel(code=404, message="Address not found", data=None)

    _clear_default_addresses(db, current_user.id, exclude_id=address.id)
    address.is_default = True
    db.add(address)
    db.commit()
    db.refresh(address)
    return ResponseModel(data=AddressOut.model_validate(address))
