import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ~3 MB de imagen en base64: suficiente para una foto JPEG de cámara frontal.
MAX_FOTO_BASE64 = 4_200_000
_CORREO = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


# Qué provocó la captura. La app toma la foto al activar el modo señuelo y, si el
# usuario tiene correo de seguridad, también al enviar un SOS o un pánico silencioso
# y al tocar un botón de llamada de emergencia.
TipoEvidencia = Literal["ANTI_THEFT", "SOS", "PANICO", "LLAMADA_EMERGENCIA"]


class AntiTheftAlertRequest(BaseModel):
    """Evidencia (foto y ubicación) enviada por la app del usuario autenticado.

    El usuario y el correo de destino NO viajan en el cuerpo: salen de la sesión
    y del correo de seguridad que el propio usuario guardó. Los campos `usuario`,
    `dispositivo_id` y `correo_destino` se aceptan por compatibilidad y se ignoran.
    """

    usuario: Optional[str] = None
    dispositivo_id: Optional[str] = None
    latitud: Optional[float] = Field(default=None, ge=-90, le=90)
    longitud: Optional[float] = Field(default=None, ge=-180, le=180)
    foto_base64: str = Field(..., min_length=50, max_length=MAX_FOTO_BASE64)
    correo_destino: Optional[str] = None
    tipo_evento: TipoEvidencia = "ANTI_THEFT"
    # Dato corto de contexto, p. ej. el número marcado ("105") o el id de la alerta.
    detalle: Optional[str] = Field(default=None, max_length=60, pattern=r"^[A-Za-z0-9 #+.:_-]*$")

    @model_validator(mode="after")
    def validar_coordenadas_completas(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("La latitud y la longitud deben enviarse juntas o ambas omitirse.")
        return self


class AntiTheftAlertResponse(BaseModel):
    alerta_id: int
    mensaje: str
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    mapa_url: Optional[str] = None
    email_enviado: bool
    # Por qué no salió el correo: SIN_CORREO_DE_SEGURIDAD, SMTP_NO_CONFIGURADO o ERROR_DE_ENVIO.
    motivo_sin_correo: Optional[str] = None


class SecurityContactRequest(BaseModel):
    correo: Optional[str] = Field(default=None, max_length=255)

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        correo = value.strip().lower()
        if not _CORREO.fullmatch(correo):
            raise ValueError("Escribe un correo válido, por ejemplo nombre@dominio.com.")
        return correo


class SecurityContactResponse(BaseModel):
    correo: Optional[str] = None
    # False cuando el servidor no tiene correo saliente: la evidencia se guarda pero no se envía.
    servidor_puede_enviar: bool
    # Si hay una alerta o evidencia reciente, el correo no se puede cambiar hasta esta hora (UTC).
    bloqueado_hasta: Optional[datetime] = None


class SecurityEventItem(BaseModel):
    id: int
    tipo_evento: str
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    email_enviado: bool
    creado_en: datetime


class SecurityEventPhoto(BaseModel):
    id: int
    foto: str  # data URL lista para mostrarse en un <img>
