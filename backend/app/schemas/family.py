from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FamiliarCreate(BaseModel):
    # La invitación se envía con el código de enlace que la otra persona comparte
    # (el que ve como "Mi Código"), no con su nombre de usuario: así solo puede
    # invitarte alguien a quien tú le diste tu código.
    codigo_invitado: str = Field(..., min_length=4, max_length=50)
    parentesco: str = Field(..., min_length=2, max_length=80)

    @field_validator("codigo_invitado")
    @classmethod
    def normalizar_codigo(cls, value: str) -> str:
        codigo = value.strip().upper()
        if len(codigo) < 4 or any(caracter.isspace() for caracter in codigo):
            raise ValueError("Escribe el código tal como aparece, por ejemplo GEO-1A2B3C.")
        return codigo


class FamiliarResponse(BaseModel):
    id: int
    usuario_responsable: str
    nombre: str
    parentesco: str
    familiar_usuario: str
    consentimiento_en: datetime
    revocado_en: Optional[datetime] = None


class FamilyInvitationResponse(BaseModel):
    id: int
    invitante_usuario: str
    invitado_usuario: str
    parentesco: str
    estado: str
    creado_en: datetime
    respondido_en: Optional[datetime] = None

    class Config:
        from_attributes = True
