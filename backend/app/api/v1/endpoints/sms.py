from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints.admin import require_rotated_platform_owner
from app.core.config import settings
from app.schemas.sms import (
    DeviceSigningKeyRequest,
    DiscardedSMSItem,
    InboundSMSResponse,
    PhoneOTPRequest,
    PhoneOTPVerifyRequest,
)
from app.services.realtime import notificar_bandejas
from app.services.sms_service import SMSService

router = APIRouter(tags=["SMS firmado"])


def get_sms_service(db: Session = Depends(get_db)) -> SMSService:
    return SMSService(db)


@router.post("/telefonos/solicitar-otp")
def solicitar_otp(
    payload: PhoneOTPRequest,
    user: dict = Depends(get_current_user),
    sms_service: SMSService = Depends(get_sms_service),
):
    try:
        return sms_service.solicitar_otp(user["sub"], payload.telefono)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/telefonos/verificar-otp")
def verificar_otp(
    payload: PhoneOTPVerifyRequest,
    user: dict = Depends(get_current_user),
    sms_service: SMSService = Depends(get_sms_service),
):
    try:
        return sms_service.verificar_otp(user["sub"], payload.telefono, payload.codigo)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/dispositivos/registrar")
def registrar_dispositivo(
    payload: DeviceSigningKeyRequest,
    user: dict = Depends(get_current_user),
    sms_service: SMSService = Depends(get_sms_service),
):
    try:
        return sms_service.registrar_dispositivo(user["sub"], payload.dispositivo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/dispositivos/{device_id}/revocar")
def revocar_dispositivo(
    device_id: str,
    user: dict = Depends(get_current_user),
    sms_service: SMSService = Depends(get_sms_service),
):
    if not sms_service.revocar_dispositivo(user["sub"], device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo firmante no encontrado.")
    return {"revocado": True}


@router.post("/sms/entrante", response_model=InboundSMSResponse)
async def sms_entrante(
    request: Request,
    sms_service: SMSService = Depends(get_sms_service),
):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook SMS demasiado grande.")
    result = sms_service.procesar_webhook(
        url=settings.SMS_WEBHOOK_PUBLIC_URL or str(request.url),
        headers=dict(request.headers),
        raw_body=bytes(body),
        content_type=request.headers.get("content-type", ""),
    )
    if result["resultado"] == "FIRMA_PROVEEDOR_INVALIDA":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma del proveedor SMS inválida.")
    if result.get("aceptado") and result.get("alerta_id"):
        await notificar_bandejas(
            sms_service.alert_service.instituciones_asignadas(result["alerta_id"]),
            result["alerta_id"],
            "alert.updated",
        )
    return result


@router.get("/sms/descartados", response_model=list[DiscardedSMSItem])
def listar_sms_descartados(
    limit: int = 100,
    _: dict = Depends(require_rotated_platform_owner),
    sms_service: SMSService = Depends(get_sms_service),
):
    return sms_service.listar_descartados(limit)
