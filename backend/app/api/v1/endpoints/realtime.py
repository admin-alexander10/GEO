from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import build_permissions_for_role, decode_access_token, normalize_role
from app.models.subscription import InstitutionAccount
from app.models.user import Usuario
from app.services.realtime import institutional_alert_hub

router = APIRouter(prefix="/realtime", tags=["Tiempo real"])


@router.websocket("/ws/alerts")
async def alertas_en_tiempo_real(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        credentials = await websocket.receive_json()
        token = credentials.get("token", "") if isinstance(credentials, dict) else ""
    except (WebSocketDisconnect, ValueError):
        return
    payload = decode_access_token(token)
    username = payload.get("sub") if payload else None
    account = db.query(Usuario).filter(Usuario.usuario == username).first() if username else None
    role = normalize_role(account.rol) if account else "ciudadano"
    permissions = set(build_permissions_for_role(role)) if account and getattr(account, "is_active", 1) else set()
    if not payload or "alert:view" not in (permissions or set(build_permissions_for_role(role))):
        await websocket.close(code=4401)
        return

    institution = getattr(account, "institucion", None) if account else None
    account_record = db.query(InstitutionAccount).filter(
        InstitutionAccount.institution_name == institution,
        InstitutionAccount.is_active.is_(True),
    ).first() if institution and institution != "individual" else None
    if not institution or institution == "individual" or role == "ciudadano" or not account_record:
        await websocket.close(code=4403)
        return

    institutional_alert_hub.connect(institution, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        institutional_alert_hub.disconnect(institution, websocket)
