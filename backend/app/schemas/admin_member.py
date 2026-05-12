from typing import Optional

from pydantic import BaseModel


class AdminMemberSummaryOut(BaseModel):
    total_users: int
    member_users: int
    non_member_users: int
    total_points: int
    unrevealed_coupons: int
    available_coupons: int
    reserved_coupons: int
    used_coupons: int


class AdminMemberUserOut(BaseModel):
    id: int
    display_id: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    is_member: bool
    invite_code: Optional[str] = None
    invited_by_user_id: Optional[int] = None
    invited_by_code: Optional[str] = None
    points: int
    coupon_count: int
    available_coupon_count: int
    order_count: int
    total_spent: str
    created_at: Optional[str] = None
    member_joined_at: Optional[str] = None


class AdminMemberUserPageOut(BaseModel):
    items: list[AdminMemberUserOut]
    total: int
    page: int
    page_size: int
    summary: AdminMemberSummaryOut


class AdminRawUserOut(BaseModel):
    id: int
    openid: str
    public_uid: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    is_registered: bool
    is_member: bool
    invite_code: Optional[str] = None
    invited_by_user_id: Optional[int] = None
    invited_by_code: Optional[str] = None
    points: int
    total_spent: str
    registered_at: Optional[str] = None
    member_joined_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    order_count: int = 0
    coupon_count: int = 0


class AdminRawUserPageOut(BaseModel):
    items: list[AdminRawUserOut]
    total: int
    page: int
    page_size: int


class AdminCouponOut(BaseModel):
    id: int
    user_id: int
    title: str
    display_title: str
    amount: Optional[str] = None
    status: str
    locked_order_id: Optional[int] = None
    created_at: Optional[str] = None
    revealed_at: Optional[str] = None
    used_at: Optional[str] = None


class AdminPointAdjustIn(BaseModel):
    amount: int
    reason: Optional[str] = None


class AdminCouponIssueIn(BaseModel):
    title: Optional[str] = None
    amount: Optional[str] = None
    status: str = "unrevealed"


class AdminMemberStatusIn(BaseModel):
    is_member: bool
