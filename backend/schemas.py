# Capa de compatibilidad retroactiva hacia app.schemas
from app.schemas.alert import AlertaCreate, AlertaResponse, AlertaDetalle
from app.schemas.auth import LoginRequest, RegistroRequest, AuthResponse
from app.schemas.family import FamiliarCreate, FamiliarResponse
from app.schemas.rescue import RutaRequest, RutaResponse

__all__ = [
    "AlertaCreate", "AlertaResponse", "AlertaDetalle",
    "LoginRequest", "RegistroRequest", "AuthResponse",
    "FamiliarCreate", "FamiliarResponse",
    "RutaRequest", "RutaResponse"
]