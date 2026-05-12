from typing import Optional

from pydantic import BaseModel


class CourierCreateIn(BaseModel):
    name: str
    phone: str
    password: str
    is_active: bool = True


class CourierUpdateIn(BaseModel):
    name: str
    phone: str
    password: Optional[str] = None
    is_active: bool = True


class CourierStatusUpdateIn(BaseModel):
    is_active: bool


class CourierOut(BaseModel):
    id: int
    name: str
    phone: str
    is_active: bool

    class Config:
        from_attributes = True
