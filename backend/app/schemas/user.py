from pydantic import BaseModel
from typing import Optional

class UserLoginIn(BaseModel):
    code: str

class UserOut(BaseModel):
    id: int
    display_id: str
    nickname: Optional[str]
    avatar_url: Optional[str] = None
    phone: Optional[str]
    is_registered: bool = False
    is_member: bool = False
    invite_code: Optional[str] = None
    points: int = 0
    member_level: str = "LV0"
    member_level_value: int = 0
    total_spent: str = "0.00"
    next_member_level: Optional[str] = None
    next_level_spend: Optional[str] = None
    amount_to_next_level: str = "0.00"
    level_progress_percent: int = 0
    weekly_coupon_count: int = 0
    level_benefit_text: str = ""
    
    class Config:
        from_attributes = True

class LoginOut(BaseModel):
    token: str
    user: UserOut
    is_new_user: bool = False


class UserProfileOut(BaseModel):
    id: int
    display_id: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    is_registered: bool = False
    is_member: bool = False
    invite_code: Optional[str] = None
    points: int = 0
    member_level: str = "LV0"
    member_level_value: int = 0
    total_spent: str = "0.00"
    next_member_level: Optional[str] = None
    next_level_spend: Optional[str] = None
    amount_to_next_level: str = "0.00"
    level_progress_percent: int = 0
    weekly_coupon_count: int = 0
    level_benefit_text: str = ""

    class Config:
        from_attributes = True


class UserProfileUpdateIn(BaseModel):
    nickname: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None


class UserRegisterIn(BaseModel):
    nickname: str
    avatar_url: Optional[str] = None


class MemberRegisterIn(BaseModel):
    invite_code: Optional[str] = None


class MemberOut(BaseModel):
    is_member: bool
    invite_code: Optional[str] = None
    points: int = 0
    invite_reward_points: int = 30
    member_level: str = "LV0"
    member_level_value: int = 0
    total_spent: str = "0.00"
    next_member_level: Optional[str] = None
    next_level_spend: Optional[str] = None
    amount_to_next_level: str = "0.00"
    level_progress_percent: int = 0
    weekly_coupon_count: int = 0
    level_benefit_text: str = ""


class CouponOut(BaseModel):
    id: int
    title: str
    amount: Optional[str] = None
    status: str
    display_title: str

    class Config:
        from_attributes = True


class CouponRedemptionOptionOut(BaseModel):
    id: str
    title: str
    amount: str
    points_cost: int
    user_points: int
    can_redeem: bool


class CouponRedeemIn(BaseModel):
    option_id: str


class CouponRedeemOut(BaseModel):
    coupon: CouponOut
    points: int


class AddressCreateIn(BaseModel):
    contact_name: str
    contact_phone: str
    building: str
    room_number: Optional[str] = None
    detail_address: str
    is_default: bool = False


class AddressUpdateIn(BaseModel):
    contact_name: str
    contact_phone: str
    building: str
    room_number: Optional[str] = None
    detail_address: str
    is_default: bool = False


class AddressOut(BaseModel):
    id: int
    user_id: int
    contact_name: str
    contact_phone: str
    building: str
    room_number: Optional[str] = None
    detail_address: str
    is_default: bool

    class Config:
        from_attributes = True
