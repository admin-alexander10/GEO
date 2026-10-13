from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PhoneOTPRequest(BaseModel):
    telefono: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class PhoneOTPVerifyRequest(PhoneOTPRequest):
    codigo: str = Field(pattern=r"^[0-9]{6}$")


class DeviceSigningKeyRequest(BaseModel):
    dispositivo_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class InboundSMS(BaseModel):
    remitente: str = Field(min_length=8, max_length=40)
    texto: str = Field(min_length=1, max_length=2000)
    recibido_en: Optional[datetime] = None


class InboundSMSResponse(BaseModel):
    aceptado: bool
    alerta_id: Optional[int] = None
    client_alert_id: Optional[str] = None
    resultado: str


class DiscardedSMSItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    remitente: str
    texto: str
    motivo: str
    recibido_en: datetime
