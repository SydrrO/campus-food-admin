from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models import Admin, Courier
from app.schemas.courier import CourierCreateIn, CourierOut, CourierStatusUpdateIn, CourierUpdateIn
from app.schemas.response import ResponseModel


router = APIRouter()


@router.get("/couriers", response_model=ResponseModel[list[CourierOut]])
async def list_couriers(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    couriers = db.query(Courier).order_by(Courier.id.asc()).all()
    return ResponseModel(data=couriers)


@router.post("/couriers", response_model=ResponseModel[CourierOut])
async def create_courier(
    payload: CourierCreateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    exists = db.query(Courier).filter(Courier.phone == payload.phone).first()
    if exists:
        return ResponseModel(code=400, message="Courier phone already exists", data=None)

    courier = Courier(
        name=payload.name,
        phone=payload.phone,
        password=get_password_hash(payload.password),
        is_active=payload.is_active,
    )
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return ResponseModel(data=courier)


@router.put("/couriers/{courier_id}", response_model=ResponseModel[CourierOut])
async def update_courier(
    courier_id: int,
    payload: CourierUpdateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        return ResponseModel(code=404, message="Courier not found", data=None)

    exists = db.query(Courier).filter(Courier.phone == payload.phone, Courier.id != courier_id).first()
    if exists:
        return ResponseModel(code=400, message="Courier phone already exists", data=None)
    courier.name = payload.name
    courier.phone = payload.phone
    if payload.password:
        courier.password = get_password_hash(payload.password)
    courier.is_active = payload.is_active
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return ResponseModel(data=courier)


@router.put("/couriers/{courier_id}/status", response_model=ResponseModel[CourierOut])
async def update_courier_status(
    courier_id: int,
    payload: CourierStatusUpdateIn,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        return ResponseModel(code=404, message="Courier not found", data=None)
    courier.is_active = payload.is_active
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return ResponseModel(data=courier)


@router.delete("/couriers/{courier_id}", response_model=ResponseModel[dict[str, bool]])
async def delete_courier(
    courier_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    courier = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        return ResponseModel(code=404, message="Courier not found", data=None)

    db.delete(courier)
    db.commit()
    return ResponseModel(data={"success": True})
