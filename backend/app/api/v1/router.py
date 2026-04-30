from fastapi import APIRouter
from app.api.v1.endpoints import admin_auth, admin_catalog, admin_config, admin_couriers, admin_finance, admin_members, admin_orders, auth, config, dishes, orders, payment, users

api_router = APIRouter()

@api_router.get("/v1/ping")
async def ping():
    return {"message": "pong"}

api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(admin_auth.router, prefix="/v1/admin/auth", tags=["admin-auth"])
api_router.include_router(admin_catalog.router, prefix="/v1/admin", tags=["admin-catalog"])
api_router.include_router(admin_orders.router, prefix="/v1/admin", tags=["admin-orders"])
api_router.include_router(admin_finance.router, prefix="/v1/admin", tags=["admin-finance"])
api_router.include_router(admin_members.router, prefix="/v1/admin", tags=["admin-members"])
api_router.include_router(admin_config.router, prefix="/v1/admin", tags=["admin-config"])
api_router.include_router(admin_couriers.router, prefix="/v1/admin", tags=["admin-couriers"])
api_router.include_router(users.router, prefix="/v1/users", tags=["users"])
api_router.include_router(dishes.router, prefix="/v1/dishes", tags=["dishes"])
api_router.include_router(orders.router, prefix="/v1/orders", tags=["orders"])
api_router.include_router(payment.router, prefix="/v1/payment", tags=["payment"])
api_router.include_router(config.router, prefix="/v1/config", tags=["config"])
