from fastapi import APIRouter, Depends, status
from typing import Dict, Any
from app.services.cap_service import CAPService
from app.api.deps import get_cap_service

router = APIRouter(prefix="/cap", tags=["Interoperabilidad B2G (OASIS CAP v1.2)"])

@router.get("/alertas/{alerta_id}/", status_code=status.HTTP_200_OK)
def exportar_alerta_cap(
    alerta_id: int,
    cap_service: CAPService = Depends(get_cap_service)
) -> Dict[str, Any]:
    """
    Exporta una alerta de rescate al estándar internacional OASIS CAP v1.2.
    Permite la ingesta directa por sistemas gubernamentales como INDECI, COER y SINAGERD.
    """
    return cap_service.exportar_alerta_cap(alerta_id)
