# Wrapper de compatibilidad hacia atrás
from sqlalchemy.orm import Session
from app.schemas.coaccion import RoboCoaccionCreate, RoboCoaccionResponse
from app.services.coaccion_service import CoaccionService

def despachar_robo_coaccion(db: Session, alerta_in: RoboCoaccionCreate) -> RoboCoaccionResponse:
    """Delega al nuevo servicio de la capa de aplicación CoaccionService."""
    servicio = CoaccionService(db)
    return servicio.despachar_robo_coaccion(alerta_in)
