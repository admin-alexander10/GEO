from fastapi import APIRouter, Depends, status
from app.schemas.coaccion import RoboCoaccionCreate, RoboCoaccionResponse
from app.services.coaccion_service import CoaccionService
from app.api.deps import get_coaccion_service, require_permission
from app.services.realtime import notificar_bandejas

router = APIRouter(prefix="/coaccion", tags=["Protocolo Silencioso"])

@router.post("/alertar/", response_model=RoboCoaccionResponse, status_code=status.HTTP_201_CREATED)
async def alertar_robo_coaccion(
    data: RoboCoaccionCreate,
    coaccion_service: CoaccionService = Depends(get_coaccion_service),
    user: dict = Depends(require_permission("alert:dispatch")),
):
    """
    Controlador para despacho de alertas de robo, asalto o coacción.
    Mantiene la discreción en el dispositivo y prioriza a la PNP.
    """
    data.usuario = user["sub"]
    data.dispositivo_id = user["sub"]
    respuesta = coaccion_service.despachar_robo_coaccion(data)
    await notificar_bandejas(respuesta.enrutamiento_institucional.get("instituciones"), respuesta.alerta_id)
    return respuesta
