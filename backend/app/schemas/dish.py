from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class DishOut(BaseModel):
    id: int
    category_id: int
    name: str
    description: Optional[str]
    detail_content: Optional[str]
    image_url: Optional[str]
    price: Decimal
    stock: int
    sort_order: int
    is_active: bool
    is_sold_out: bool
    
    class Config:
        from_attributes = True
