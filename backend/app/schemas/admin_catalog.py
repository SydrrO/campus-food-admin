from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class CategoryCreateIn(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdateIn(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class CategoryAdminOut(BaseModel):
    id: int
    name: str
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class DishCreateIn(BaseModel):
    category_id: int
    name: str
    description: Optional[str] = None
    detail_content: Optional[str] = None
    image_url: Optional[str] = None
    price: Decimal
    stock: int = -1
    sort_order: int = 0
    is_active: bool = True
    is_sold_out: bool = False


class DishUpdateIn(BaseModel):
    category_id: int
    name: str
    description: Optional[str] = None
    detail_content: Optional[str] = None
    image_url: Optional[str] = None
    price: Decimal
    stock: int = -1
    sort_order: int = 0
    is_active: bool = True
    is_sold_out: bool = False


class DishStatusUpdateIn(BaseModel):
    is_active: bool


class DishAdminOut(BaseModel):
    id: int
    category_id: int
    name: str
    description: Optional[str] = None
    detail_content: Optional[str] = None
    image_url: Optional[str] = None
    price: Decimal
    stock: int
    sort_order: int
    is_active: bool
    is_sold_out: bool

    class Config:
        from_attributes = True
