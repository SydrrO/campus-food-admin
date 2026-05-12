from typing import Optional

from pydantic import BaseModel


class AdminLoginIn(BaseModel):
    username: str
    password: str


class AdminOut(BaseModel):
    id: int
    username: str
    real_name: Optional[str] = None
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class AdminLoginOut(BaseModel):
    token: str
    admin: AdminOut
