import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from uuid import UUID

class AlertaCreate(BaseModel):
    client_alert_id: Optional[str] = None
    dispositivo_id: Optional[str] = None
    usuario: Optional[str] = None
    tipo_emergencia: str = Field(default="Sismo SOS")
    nivel_gravedad: int = Field(default=3, ge=1, le=5)
    latitud: Optional[float] = Field(default=None, ge=-90, le=90)
    longitud: Optional[float] = Field(default=None, ge=-180, le=180)
    origen_alerta: Literal["MANUAL", "AUTOMATICO_INERCIA"] = "MANUAL"
    estado_confirmacion: Literal[
        "CONFIRMADO",
        "SIN_RESPUESTA_AL_CONTEO",
        "EXPIRADO_INCONSCIENTE",
        "CANCELADO_USUARIO",
        "EN_EVALUACION",
    ] = "CONFIRMADO"
    timestamp_dispositivo: Optional[datetime] = None
    precision_m: Optional[int] = Field(default=None, ge=0, le=100000)
    edad_lectura_s: Optional[int] = Field(default=None, ge=0, le=31536000)
    es_simulacro: bool = False

    @field_validator("client_alert_id", mode="before")
    @classmethod
    def validar_client_alert_id(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        if not isinstance(value, str):
            raise ValueError("client_alert_id debe ser un UUID o 10 caracteres Base32.")
        try:
            return str(UUID(value))
        except ValueError:
            pass
        if re.fullmatch(r"[A-Z2-7]{10}", value, flags=re.IGNORECASE):
            return value.upper()
        raise ValueError("client_alert_id debe ser un UUID o 10 caracteres Base32.")

    @model_validator(mode='before')
    @classmethod
    def normalizar_campos(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalizar longitude -> longitud
            if "longitude" in data and "longitud" not in data:
                data["longitud"] = data["longitude"]
            # Asegurar dispositivo_id
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


class AlertStateUpdate(BaseModel):
    estado: Literal["RECIBIDA", "EN_ATENCION", "ATENDIDA", "RESUELTA", "CANCELADA"]
    motivo: Optional[str] = Field(default=None, max_length=500)


class EnrutamientoInstitucional(BaseModel):
    # SIN_COBERTURA_CONFIRMADA: ninguna institución con cobertura validada la tiene.
    # EN_BANDEJA_INSTITUCIONAL: está visible en la bandeja de `instituciones`;
    # no significa que alguien la haya leído ni que haya una unidad en camino.
    estado: str = "SIN_COBERTURA_CONFIRMADA"
    departamento: Optional[str] = None
    institucion_responsable: Optional[str] = None
    instituciones: List[str] = Field(default_factory=list)
    prioridad: int
    tiempo_estimado_despliegue: Optional[str] = None

class NotificacionFamiliar(BaseModel):
    estado: str = "NO_CONFIRMADA"
    familiares_alertados: List[str] = Field(default_factory=list)
    canal: Optional[str] = None

class RecursoAsignado(BaseModel):
    unidad: Optional[str] = None
    estado: Optional[str] = None

class AlertaResponse(BaseModel):
    estado: str
    alerta_id: int
    client_alert_id: Optional[str] = None
    origen: str = "MANUAL"
    confirmacion: str = "CONFIRMADO"
    coordenadas: Optional[Dict[str, float]] = None
    enrutamiento_institucional: Optional[EnrutamientoInstitucional] = None
    notificacion_familiar: NotificacionFamiliar = Field(default_factory=NotificacionFamiliar)
    recurso_asignado: Optional[RecursoAsignado] = None
    creado_en: Optional[datetime] = None

class AlertaDetalle(BaseModel):
    id: int
    dispositivo_id: str
    usuario: Optional[str] = None
    tipo_emergencia: str
    nivel_gravedad: Optional[int] = 3
    origen_alerta: Optional[str] = "MANUAL"
    estado_confirmacion: Optional[str] = "CONFIRMADO"
    estado: str = "REGISTRADA"
    client_alert_id: Optional[str] = None
    canal_entrada: str = "API"
    precision_m: Optional[int] = None
    edad_lectura_s: Optional[int] = None
    es_simulacro: bool = False
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    timestamp_dispositivo: Optional[datetime] = None
    creado_en: Optional[datetime] = None


class AlertaSinAsignar(BaseModel):
    """Alerta abierta que ninguna institución tiene en su bandeja (vista del propietario)."""
    id: int
    usuario: Optional[str] = None
    tipo_emergencia: str
    nivel_gravedad: Optional[int] = None
    origen_alerta: Optional[str] = None
    estado: str
    canal_entrada: str = "API"
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    creado_en: Optional[datetime] = None
    instituciones_en_cobertura: List[str] = Field(default_factory=list)


class AsignacionManualRequest(BaseModel):
    institution_name: str = Field(..., min_length=2, max_length=120)
    reason: str = Field(..., min_length=10, max_length=500)


class AsignacionManualResponse(BaseModel):
    alerta_id: int
    estado: str
    instituciones: List[str]
