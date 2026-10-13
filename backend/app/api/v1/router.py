from fastapi import APIRouter
from app.api.v1.endpoints import admin, auth, family, alerts, rescue, coaccion, cap, security, subscriptions, realtime, sms, directory

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(family.router)
api_router.include_router(alerts.router)
api_router.include_router(rescue.router)
api_router.include_router(coaccion.router)
api_router.include_router(cap.router)
api_router.include_router(security.router)
api_router.include_router(subscriptions.router)
api_router.include_router(realtime.router)
api_router.include_router(admin.router)
api_router.include_router(sms.router)
api_router.include_router(directory.router)
