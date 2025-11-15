from fastapi import APIRouter
from fastapi.responses import JSONResponse
import app.routers.schedule as schedule

router = APIRouter(prefix="/api")
router.include_router(schedule.router)

# Root router for health check and info
root_router = APIRouter()


@root_router.get("/")
async def root():
    """Корневой эндпоинт для проверки работы API"""
    return JSONResponse({
        "message": "MISIS Schedule API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "api": "/api"
    })


@root_router.get("/health")
async def health():
    """Health check endpoint"""
    return JSONResponse({"status": "ok"})
