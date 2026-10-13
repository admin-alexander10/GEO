from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.alert import AlertStateUpdate, AlertaCreate, AlertaResponse, AlertaDetalle
from app.services.alert_service import AlertService
from app.api.deps import get_alert_service, get_current_user, require_permission
from app.services.realtime import notificar_bandejas

router = APIRouter(prefix="/alertas", tags=["Alertas de Emergencia"])

@router.post("/despachar/", response_model=AlertaResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("alert:dispatch"))])
async def despachar_alerta(
    data: AlertaCreate,
    user: dict = Depends(get_current_user),
    alert_service: AlertService = Depends(get_alert_service)
):
    """
    Controlador de despacho de alerta geoespacial.
    Persiste en PostGIS y activa el enrutamiento táctico institucional y familiar.
    """
    data.usuario = user["sub"]
    data.dispositivo_id = user["sub"]
    respuesta = alert_service.despachar_alerta(data)
    if respuesta.enrutamiento_institucional:
        await notificar_bandejas(respuesta.enrutamiento_institucional.instituciones, respuesta.alerta_id)
    return respuesta

@router.get("/activas/", response_model=List[AlertaDetalle])
def listar_alertas_activas(
    limit: int = 50,
    user: dict = Depends(require_permission("map:view")),
    alert_service: AlertService = Depends(get_alert_service)
):
    """Solo devuelve alertas asignadas a la institución autenticada."""
    return alert_service.listar_alertas_activas(institucion=user.get("institucion"), limit=limit)


@router.get("/buzon-familiar/", response_model=List[AlertaDetalle])
def listar_buzon_familiar(
    user: dict = Depends(require_permission("family:view")),
    alert_service: AlertService = Depends(get_alert_service),
):
    return alert_service.listar_buzon_familiar(usuario=user["sub"])


@router.patch("/{alerta_id}/estado/", response_model=AlertaDetalle)
async def cambiar_estado_alerta(
    alerta_id: int,
    cambio: AlertStateUpdate,
    user: dict = Depends(get_current_user),
    alert_service: AlertService = Depends(get_alert_service),
):
    permisos = set(user.get("permisos") or [])
    if not {"alert:dispatch", "alert:handle"}.intersection(permisos):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes cambiar estados de alertas.")
    detalle = alert_service.cambiar_estado(
        alerta_id=alerta_id,
        usuario=user["sub"],
        rol=user["rol"],
        institucion=user.get("institucion"),
        cambio=cambio,
    )
    await notificar_bandejas(alert_service.instituciones_asignadas(alerta_id), alerta_id, "alert.updated")
    return detalle
