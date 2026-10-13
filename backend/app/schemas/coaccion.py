from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


class RoboCoaccionCreate(BaseModel):
    client_alert_id: UUID
    dispositivo_id: Optional[str] = None
    usuario: Optional[str] = None
    tipo_amenaza: str = Field(default="coaccion")
    descripcion: str = Field(default="Amenaza de robo o coacción")
    amenaza_detectada: bool = False
    activar_panic_silencioso: bool = False
    nivel_gravedad: int = Field(default=5, ge=1, le=5)
    latitud: Optional[float] = Field(default=None, ge=-90, le=90)
    longitud: Optional[float] = Field(default=None, ge=-180, le=180)
    timestamp_dispositivo: Optional[datetime] = None

    @model_validator(mode='before')
    @classmethod
    def normalizar_campos(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "longitude" in data and "longitud" not in data:
                data["longitud"] = data["longitude"]
            if "usuario" in data and not data.get("dispositivo_id"):
                data["dispositivo_id"] = data["usuario"]
            elif "dispositivo_id" in data and not data.get("usuario"):
                data["usuario"] = data["dispositivo_id"]
        return data

    @model_validator(mode="after")
    def validar_coordenadas_completas(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("La latitud y la longitud deben enviarse juntas o ambas omitirse.")
        return self

class RoboCoaccionResponse(BaseModel):
    estado: str
    alerta_id: int
    client_alert_id: UUID
    tipo_emergencia: str = "ROBO_ASALTO_COACCION"
    institucion_prioritaria: Optional[str] = None
    prioridad: int = 5
    alerta_silenciosa: bool = True
    coordenadas: Optional[Dict[str, float]] = None
    enrutamiento_institucional: Dict[str, Any]
    notificacion_familiar: Dict[str, Any]
    recurso_asignado: Optional[Dict[str, str]] = None
