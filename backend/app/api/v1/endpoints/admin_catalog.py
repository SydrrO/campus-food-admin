from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import Admin, Category, Dish
from app.schemas.admin_catalog import CategoryAdminOut, CategoryCreateIn, CategoryUpdateIn, DishAdminOut, DishCreateIn, DishStatusUpdateIn, DishUpdateIn
from app.schemas.response import ResponseModel


router = APIRouter()


@router.get("/categories", response_model=ResponseModel[list[CategoryAdminOut]])
async def list_categories(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    categories = db.query(Category).order_by(Category.sort_order.asc(), Category.id.asc()).all()
    return ResponseModel(data=categories)


@router.post("/categories", response_model=ResponseModel[CategoryAdminOut])
async def create_category(
    payload: CategoryCreateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = Category(name=payload.name, sort_order=payload.sort_order, is_active=payload.is_active)
    db.add(category)
    db.commit()
    db.refresh(category)
    return ResponseModel(data=category)


@router.put("/categories/{category_id}", response_model=ResponseModel[CategoryAdminOut])
async def update_category(
    category_id: int,
    payload: CategoryUpdateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return ResponseModel(code=404, message="Category not found", data=None)

    category.name = payload.name
    category.sort_order = payload.sort_order
    category.is_active = payload.is_active
    db.add(category)
    db.commit()
    db.refresh(category)
    return ResponseModel(data=category)


@router.delete("/categories/{category_id}", response_model=ResponseModel[dict[str, bool]])
async def delete_category(
    category_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return ResponseModel(code=404, message="Category not found", data=None)

    dish_exists = db.query(Dish.id).filter(Dish.category_id == category_id).first() is not None
    if dish_exists:
        return ResponseModel(code=400, message="Category has dishes and cannot be deleted", data=None)

    db.delete(category)
    db.commit()
    return ResponseModel(data={"success": True})


@router.get("/dishes", response_model=ResponseModel[list[DishAdminOut]])
async def list_dishes(
    page: int = 1,
    page_size: int = Query(100, ge=1, le=500),
    category_id: int | None = Query(None),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Dish)
    if category_id is not None:
        query = query.filter(Dish.category_id == category_id)
    dishes = (
        query.order_by(Dish.sort_order.asc(), Dish.id.asc())
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
        .all()
    )
    return ResponseModel(data=dishes)


@router.post("/dishes", response_model=ResponseModel[DishAdminOut])
async def create_dish(
    payload: DishCreateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if not category:
        return ResponseModel(code=404, message="Category not found", data=None)

    dish = Dish(
        category_id=payload.category_id,
        name=payload.name,
        description=payload.description,
        detail_content=payload.detail_content,
        image_url=payload.image_url,
        price=payload.price,
        cost_price=payload.cost_price,
        stock=payload.stock,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        is_sold_out=payload.is_sold_out,
    )
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return ResponseModel(data=dish)


@router.put("/dishes/{dish_id}", response_model=ResponseModel[DishAdminOut])
async def update_dish(
    dish_id: int,
    payload: DishUpdateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    dish = db.query(Dish).filter(Dish.id == dish_id).first()
    if not dish:
        return ResponseModel(code=404, message="Dish not found", data=None)

    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if not category:
        return ResponseModel(code=404, message="Category not found", data=None)

    dish.category_id = payload.category_id
    dish.name = payload.name
    dish.description = payload.description
    dish.detail_content = payload.detail_content
    dish.image_url = payload.image_url
    dish.price = payload.price
    dish.cost_price = payload.cost_price
    dish.stock = payload.stock
    dish.sort_order = payload.sort_order
    dish.is_active = payload.is_active
    dish.is_sold_out = payload.is_sold_out
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return ResponseModel(data=dish)


@router.delete("/dishes/{dish_id}", response_model=ResponseModel[dict[str, bool]])
async def delete_dish(
    dish_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    dish = db.query(Dish).filter(Dish.id == dish_id).first()
    if not dish:
        return ResponseModel(code=404, message="Dish not found", data=None)

    db.delete(dish)
    db.commit()
    return ResponseModel(data={"success": True})


@router.put("/dishes/{dish_id}/status", response_model=ResponseModel[DishAdminOut])
async def update_dish_status(
    dish_id: int,
    payload: DishStatusUpdateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    dish = db.query(Dish).filter(Dish.id == dish_id).first()
    if not dish:
        return ResponseModel(code=404, message="Dish not found", data=None)

    dish.is_active = payload.is_active
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return ResponseModel(data=dish)
