# Wrapper de compatibilidad hacia atrás
from sqlalchemy.orm import Session
from app.schemas.alert import AlertaCreate, AlertaResponse
from app.services.alert_service import AlertService

def despachar_alerta_servicio(db: Session, alerta_in: AlertaCreate) -> AlertaResponse:
    """Delega al nuevo servicio de la capa de aplicación AlertService."""
    servicio = AlertService(db)
    return servicio.despachar_alerta(alerta_in)
