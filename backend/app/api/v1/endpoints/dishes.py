from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.models import Category, Dish
from app.schemas.category import CategoryOut
from app.schemas.dish import DishOut
from app.schemas.response import ResponseModel

router = APIRouter()

@router.get("/categories", response_model=ResponseModel[List[CategoryOut]])
async def get_categories(db: Session = Depends(get_db)):
    """获取分类列表"""
    categories = db.query(Category).filter(Category.is_active == True).order_by(Category.sort_order).all()
    return ResponseModel(data=categories)

@router.get("", response_model=ResponseModel[List[DishOut]])
async def get_dishes(
    category_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取餐品列表"""
    query = db.query(Dish).filter(Dish.is_active == True)
    if category_id:
        query = query.filter(Dish.category_id == category_id)
    if keyword:
        keyword = keyword.strip()
        if keyword:
            like_pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    Dish.name.ilike(like_pattern),
                    Dish.description.ilike(like_pattern),
                )
            )
    dishes = query.order_by(Dish.sort_order).all()
    return ResponseModel(data=dishes)

@router.get("/{dish_id}", response_model=ResponseModel[DishOut])
async def get_dish_detail(dish_id: int, db: Session = Depends(get_db)):
    """获取餐品详情"""
    dish = db.query(Dish).filter(Dish.id == dish_id, Dish.is_active == True).first()
    if not dish:
        return ResponseModel(code=404, message="Dish not found", data=None)
    return ResponseModel(data=dish)
