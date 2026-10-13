from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.security import (
    AntiTheftAlertRequest,
    AntiTheftAlertResponse,
    SecurityContactRequest,
    SecurityContactResponse,
    SecurityEventItem,
    SecurityEventPhoto,
)
from app.services.security_service import CorreoBloqueado, SecurityService

router = APIRouter(prefix="/security", tags=["Seguridad Inteligente"])


@router.post(
    "/anti-theft-alert",
    response_model=AntiTheftAlertResponse,
    status_code=status.HTTP_201_CREATED,
)
def anti_theft_alert(
    payload: AntiTheftAlertRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Guarda la foto y la ubicación como evidencia del usuario autenticado y,
    si tiene un correo de seguridad y el servidor puede enviar, se la envía ahí.
    Sirve para el modo antirrobo y para las capturas automáticas de SOS, pánico
    y llamadas de emergencia (campo `tipo_evento`)."""
    service = SecurityService(db)
    if service.limite_alcanzado(user["sub"]):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ya registraste varias evidencias en la última hora. Inténtalo más tarde.",
        )
    return service.process_anti_theft_alert(user["sub"], payload)


@router.get("/contact", response_model=SecurityContactResponse)
def obtener_correo_de_seguridad(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return SecurityService(db).obtener_contacto(user["sub"])


@router.put("/contact", response_model=SecurityContactResponse)
def guardar_correo_de_seguridad(
    payload: SecurityContactRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Guarda (o borra, si llega vacío) el correo al que se envían las evidencias.
    Tras un SOS, pánico o evidencia reciente, el correo ya guardado queda bloqueado."""
    try:
        return SecurityService(db).guardar_contacto(user["sub"], payload.correo)
    except CorreoBloqueado as bloqueo:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "El correo de seguridad está bloqueado porque hay una alerta o evidencia reciente. "
                f"Podrás cambiarlo después del {bloqueo.hasta.strftime('%d/%m/%Y %H:%M')} UTC."
            ),
        )


@router.get("/events", response_model=List[SecurityEventItem])
def listar_mis_evidencias(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return SecurityService(db).listar_eventos(user["sub"])


@router.get("/events/{evento_id}/photo", response_model=SecurityEventPhoto)
def ver_foto_de_evidencia(
    evento_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return SecurityService(db).obtener_foto(user["sub"], evento_id)
