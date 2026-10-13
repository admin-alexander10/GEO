# Wrapper de compatibilidad hacia atrás
from app.schemas.rescue import RutaRequest, RutaResponse
from app.services.rescue_service import RescueService

def calcular_ruta_rescate(ruta_in: RutaRequest) -> RutaResponse:
    """Delega al nuevo servicio de la capa de aplicación RescueService."""
    servicio = RescueService()
    return servicio.calcular_ruta_rescate(ruta_in)
