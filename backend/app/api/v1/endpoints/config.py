from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import SystemConfig
from app.schemas.config import ConfigOut
from app.schemas.response import ResponseModel

router = APIRouter()

@router.get("", response_model=ResponseModel[ConfigOut])
async def get_config(db: Session = Depends(get_db)):
    """获取系统配置"""
    configs = db.query(SystemConfig).all()
    config_dict = {c.config_key: c.config_value for c in configs}
    
    return ResponseModel(data=ConfigOut(
        lunch_deadline=config_dict.get("lunch_deadline", "10:30"),
        dinner_deadline=config_dict.get("dinner_deadline", "16:00"),
        payment_timeout=config_dict.get("payment_timeout", "15"),
        base_delivery_fee=config_dict.get("base_delivery_fee", "1"),
    ))
