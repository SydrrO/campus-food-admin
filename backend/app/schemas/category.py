from pydantic import BaseModel

class CategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    is_active: bool
    
    class Config:
        from_attributes = True
