import random
import string
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import Address, Admin, Order, OrderStatus, User, UserCoupon
from app.schemas.admin_member import (
    AdminCouponIssueIn,
    AdminCouponOut,
    AdminMemberStatusIn,
    AdminMemberSummaryOut,
    AdminMemberUserOut,
    AdminMemberUserPageOut,
    AdminPointAdjustIn,
    AdminRawUserOut,
    AdminRawUserPageOut,
)
from app.schemas.response import ResponseModel
from app.utils.timezone import now_china


router = APIRouter()

INVITE_CODE_ALPHABET = string.ascii_letters + string.digits
VALID_COUPON_STATUSES = {"unrevealed", "available", "reserved", "used"}


def _display_id(public_uid: str | None) -> str:
    if not public_uid:
        return "ID 待生成"
    if len(public_uid) <= 10:
        return public_uid
    return f"{public_uid[:4]}...{public_uid[-4:]}"


def _coupon_display_title(coupon: UserCoupon) -> str:
    if coupon.status == "unrevealed" or coupon.amount is None:
        return "随机立减券"
    amount_text = format(Decimal(str(coupon.amount)).quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
    return f"{amount_text}元券"


def _generate_invite_code(db: Session) -> str:
    for _ in range(50):
        value = "".join(random.choices(INVITE_CODE_ALPHABET, k=5))
        if not db.query(User.id).filter(User.invite_code == value).first():
            return value
    raise RuntimeError("Failed to generate invite code")


def _serialize_coupon(coupon: UserCoupon) -> AdminCouponOut:
    return AdminCouponOut(
        id=int(coupon.id),
        user_id=int(coupon.user_id),
        title=coupon.title,
        display_title=_coupon_display_title(coupon),
        amount=str(coupon.amount) if coupon.amount is not None else None,
        status=coupon.status,
        locked_order_id=int(coupon.locked_order_id) if coupon.locked_order_id else None,
        created_at=coupon.created_at.isoformat() if coupon.created_at else None,
        revealed_at=coupon.revealed_at.isoformat() if coupon.revealed_at else None,
        used_at=coupon.used_at.isoformat() if coupon.used_at else None,
    )


def _build_summary(db: Session) -> AdminMemberSummaryOut:
    total_users = db.query(User).count()
    member_users = db.query(User).filter(User.is_member.is_(True)).count()
    total_points = db.query(func.coalesce(func.sum(User.points), 0)).scalar() or 0
    coupon_counts = {
        status: db.query(UserCoupon).filter(UserCoupon.status == status).count()
        for status in VALID_COUPON_STATUSES
    }
    return AdminMemberSummaryOut(
        total_users=total_users,
        member_users=member_users,
        non_member_users=max(total_users - member_users, 0),
        total_points=int(total_points),
        unrevealed_coupons=coupon_counts.get("unrevealed", 0),
        available_coupons=coupon_counts.get("available", 0),
        reserved_coupons=coupon_counts.get("reserved", 0),
        used_coupons=coupon_counts.get("used", 0),
    )


def _serialize_user(db: Session, user: User) -> AdminMemberUserOut:
    coupons = db.query(UserCoupon).filter(UserCoupon.user_id == user.id).all()
    paid_orders = (
        db.query(Order)
        .filter(Order.user_id == user.id, Order.paid_at.isnot(None), Order.status != OrderStatus.closed)
        .all()
    )
    total_spent = Decimal(str(user.total_spent or "0.00"))
    return AdminMemberUserOut(
        id=int(user.id),
        display_id=_display_id(user.public_uid),
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        phone=user.phone,
        is_member=bool(user.is_member),
        invite_code=user.invite_code,
        invited_by_user_id=int(user.invited_by_user_id) if user.invited_by_user_id else None,
        points=user.points or 0,
        coupon_count=len(coupons),
        available_coupon_count=sum(1 for coupon in coupons if coupon.status in {"unrevealed", "available"}),
        order_count=len(paid_orders),
        total_spent=str(total_spent),
        created_at=user.created_at.isoformat() if user.created_at else None,
        member_joined_at=user.member_joined_at.isoformat() if user.member_joined_at else None,
    )


def _default_contact_phone(db: Session, user: User, order_count: int) -> str | None:
    if order_count <= 0:
        return None

    default_address = (
        db.query(Address)
        .filter(Address.user_id == user.id, Address.is_default.is_(True))
        .order_by(Address.updated_at.desc(), Address.id.desc())
        .first()
    )
    if default_address and default_address.contact_phone:
        return default_address.contact_phone

    latest_order = (
        db.query(Order)
        .filter(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .first()
    )
    return latest_order.contact_phone if latest_order and latest_order.contact_phone else None


def _serialize_raw_user(db: Session, user: User) -> AdminRawUserOut:
    order_count = db.query(Order.id).filter(Order.user_id == user.id).count()
    coupon_count = db.query(UserCoupon.id).filter(UserCoupon.user_id == user.id).count()
    return AdminRawUserOut(
        id=int(user.id),
        openid=user.openid,
        public_uid=user.public_uid,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        phone=_default_contact_phone(db, user, order_count),
        is_registered=bool(user.is_registered),
        is_member=bool(user.is_member),
        invite_code=user.invite_code,
        invited_by_user_id=int(user.invited_by_user_id) if user.invited_by_user_id else None,
        points=int(user.points or 0),
        total_spent=str(user.total_spent or "0.00"),
        registered_at=user.registered_at.isoformat() if user.registered_at else None,
        member_joined_at=user.member_joined_at.isoformat() if user.member_joined_at else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
        order_count=order_count,
        coupon_count=coupon_count,
    )


def _build_user_query(
    db: Session,
    *,
    keyword: str | None = None,
    member_status: str | None = None,
    coupon_status: str | None = None,
):
    query = db.query(User)
    if member_status == "member":
        query = query.filter(User.is_member.is_(True))
    elif member_status == "non_member":
        query = query.filter(User.is_member.is_(False))

    if coupon_status in VALID_COUPON_STATUSES:
        user_ids = select(UserCoupon.user_id).where(UserCoupon.status == coupon_status)
        query = query.filter(User.id.in_(user_ids))

    if keyword:
        value = keyword.strip()
        if value:
            like_value = f"%{value}%"
            query = query.filter(
                or_(
                    User.public_uid.ilike(like_value),
                    User.nickname.ilike(like_value),
                    User.phone.ilike(like_value),
                    User.id.in_(select(Address.user_id).where(Address.contact_phone.ilike(like_value))),
                    User.id.in_(select(Order.user_id).where(Order.contact_phone.ilike(like_value))),
                    User.invite_code.ilike(like_value),
                )
            )
    return query


@router.get("/members/summary", response_model=ResponseModel[AdminMemberSummaryOut])
async def get_member_summary(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return ResponseModel(data=_build_summary(db))


@router.get("/members/users", response_model=ResponseModel[AdminMemberUserPageOut])
async def list_member_users(
    keyword: str | None = Query(None),
    member_status: str | None = Query(None),
    coupon_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = _build_user_query(
        db,
        keyword=keyword,
        member_status=member_status,
        coupon_status=coupon_status,
    )
    total = query.count()
    users = (
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ResponseModel(
        data=AdminMemberUserPageOut(
            items=[_serialize_user(db, user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            summary=_build_summary(db),
        )
    )


@router.get("/users", response_model=ResponseModel[AdminRawUserPageOut])
async def list_raw_users(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = _build_user_query(db, keyword=keyword)
    total = query.count()
    users = (
        query.order_by(User.total_spent.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ResponseModel(
        data=AdminRawUserPageOut(
            items=[_serialize_raw_user(db, user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/users/{user_id}", response_model=ResponseModel[AdminRawUserOut])
async def get_raw_user(
    user_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    return ResponseModel(data=_serialize_raw_user(db, user))


@router.get("/members/users/{user_id}/coupons", response_model=ResponseModel[list[AdminCouponOut]])
async def list_user_coupons(
    user_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    coupons = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user_id)
        .order_by(UserCoupon.id.desc())
        .all()
    )
    return ResponseModel(data=[_serialize_coupon(coupon) for coupon in coupons])


@router.put("/members/users/{user_id}/member", response_model=ResponseModel[AdminMemberUserOut])
async def update_user_member_status(
    user_id: int,
    payload: AdminMemberStatusIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    user.is_member = payload.is_member
    if payload.is_member and not user.invite_code:
        user.invite_code = _generate_invite_code(db)
    db.add(user)
    db.commit()
    db.refresh(user)
    return ResponseModel(data=_serialize_user(db, user))


@router.post("/members/users/{user_id}/points", response_model=ResponseModel[AdminMemberUserOut])
async def adjust_user_points(
    user_id: int,
    payload: AdminPointAdjustIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    next_points = (user.points or 0) + payload.amount
    if next_points < 0:
        return ResponseModel(code=400, message="Points cannot be negative", data=None)

    user.points = next_points
    db.add(user)
    db.commit()
    db.refresh(user)
    return ResponseModel(data=_serialize_user(db, user))


@router.post("/members/users/{user_id}/coupons", response_model=ResponseModel[AdminCouponOut])
async def issue_user_coupon(
    user_id: int,
    payload: AdminCouponIssueIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    if payload.status not in {"unrevealed", "available"}:
        return ResponseModel(code=400, message="Coupon can only be issued as unrevealed or available", data=None)

    amount = None
    revealed_at = None
    title = payload.title or "随机立减券"
    if payload.status == "available":
        try:
            amount = Decimal(str(payload.amount or "0.50")).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return ResponseModel(code=400, message="Invalid coupon amount", data=None)
        if amount <= 0:
            return ResponseModel(code=400, message="Coupon amount must be greater than zero", data=None)
        amount_text = format(amount.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
        title = payload.title or f"{amount_text}元券"
        revealed_at = now_china()

    coupon = UserCoupon(
        user_id=user_id,
        title=title,
        amount=amount,
        status=payload.status,
        revealed_at=revealed_at,
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return ResponseModel(data=_serialize_coupon(coupon))


@router.delete("/members/users/{user_id}/coupons/{coupon_id}", response_model=ResponseModel[AdminCouponOut])
async def delete_user_coupon(
    user_id: int,
    coupon_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, message="User not found", data=None)

    coupon = (
        db.query(UserCoupon)
        .filter(UserCoupon.id == coupon_id, UserCoupon.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not coupon:
        return ResponseModel(code=404, message="Coupon not found", data=None)

    if coupon.status in {"reserved", "used"}:
        return ResponseModel(code=400, message="Reserved or used coupons cannot be deleted", data=None)

    serialized = _serialize_coupon(coupon)
    db.delete(coupon)
    db.commit()
    return ResponseModel(data=serialized)
