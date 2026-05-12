import random

from app.utils.timezone import now_china

def generate_order_no() -> str:
    """生成订单号: YYYYMMDDHHMMSS + 8位随机数"""
    timestamp = now_china().strftime("%Y%m%d%H%M%S")
    random_suffix = ''.join([str(random.randint(0, 9)) for _ in range(8)])
    return timestamp + random_suffix
