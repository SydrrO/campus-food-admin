from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import Admin, SystemConfig
from app.schemas.config import ConfigOut
from app.schemas.response import ResponseModel


router = APIRouter()


@router.get("/config", response_model=ResponseModel[ConfigOut])
async def get_config(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    configs = db.query(SystemConfig).all()
    config_dict = {c.config_key: c.config_value for c in configs}
    return ResponseModel(
        data=ConfigOut(
            lunch_deadline=config_dict.get("lunch_deadline", "10:30"),
            dinner_deadline=config_dict.get("dinner_deadline", "16:00"),
            payment_timeout=config_dict.get("payment_timeout", "15"),
            base_delivery_fee=config_dict.get("base_delivery_fee", "0"),
        )
    )


@router.put("/config", response_model=ResponseModel[ConfigOut])
async def update_config(
    payload: ConfigOut,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    for key, value in values.items():
        config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        if config:
            config.config_value = str(value)
            db.add(config)
        else:
            db.add(SystemConfig(config_key=key, config_value=str(value), description=key))
    db.commit()
    return ResponseModel(data=payload)
