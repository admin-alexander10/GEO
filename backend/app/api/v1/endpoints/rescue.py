from fastapi import APIRouter, Depends
from app.schemas.rescue import RutaRequest, RutaResponse
from app.services.rescue_service import RescueService
from app.api.deps import get_rescue_service, require_permission

router = APIRouter(prefix="/rescate", tags=["Operaciones de Rescate"])

@router.post("/calcular-ruta/", response_model=RutaResponse)
def calcular_ruta(
    data: RutaRequest,
    user: dict = Depends(require_permission("map:view")),
    rescue_service: RescueService = Depends(get_rescue_service)
):
    """Controlador para cálculo de rutas de rescate con evasión de bloqueos viales."""
    return rescue_service.calcular_ruta_rescate(data)
