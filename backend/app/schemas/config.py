from pydantic import BaseModel

class ConfigOut(BaseModel):
    lunch_deadline: str
    dinner_deadline: str
    payment_timeout: str
    base_delivery_fee: str
