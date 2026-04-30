from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.router import api_router
from app.services.timeout_worker import start_timeout_worker

app = FastAPI(
    title="Campus Food Ordering System",
    version="1.0.0",
    debug=settings.APP_DEBUG
)

ADMIN_STATIC_DIR = Path(__file__).resolve().parents[2] / "campus-food-admin"
UPLOADS_DIR = Path(settings.UPLOADS_ROOT).resolve() if settings.UPLOADS_ROOT else Path(__file__).resolve().parents[1] / "uploads"
UPLOADS_PUBLIC_PATH = settings.UPLOADS_PUBLIC_PATH if settings.UPLOADS_PUBLIC_PATH.startswith("/") else f"/{settings.UPLOADS_PUBLIC_PATH}"
timeout_worker_task = None
timeout_worker_stop = None

app.include_router(api_router, prefix="/api")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(UPLOADS_PUBLIC_PATH, StaticFiles(directory=UPLOADS_DIR), name="uploads")

if ADMIN_STATIC_DIR.exists():
    @app.get("/admin", include_in_schema=False)
    async def admin_entry():
        return RedirectResponse(url="/admin/login.html")


    @app.get("/admin/", include_in_schema=False)
    async def admin_entry_with_slash():
        return RedirectResponse(url="/admin/login.html")


    app.mount("/admin", StaticFiles(directory=ADMIN_STATIC_DIR, html=True), name="admin-static")


@app.on_event("startup")
async def start_background_workers():
    global timeout_worker_task, timeout_worker_stop
    timeout_worker_task, timeout_worker_stop = start_timeout_worker(settings.REDIS_TIMEOUT_SCAN_SECONDS)


@app.on_event("shutdown")
async def stop_background_workers():
    global timeout_worker_task, timeout_worker_stop
    if timeout_worker_stop is not None:
        timeout_worker_stop.set()
    if timeout_worker_task is not None:
        await timeout_worker_task


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}
