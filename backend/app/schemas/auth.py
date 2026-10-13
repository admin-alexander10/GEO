from pydantic import BaseModel, Field
from typing import Optional, List

class LoginRequest(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=3)
    modo: str = Field(default="familiar", pattern="^(familiar|institucional)$")
    institucion: Optional[str] = Field(default=None, max_length=120)

class RegistroRequest(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4)
    modo: str = Field(default="familiar", pattern="^(familiar|institucional)$")
    nombre_institucion: Optional[str] = Field(default=None, min_length=2, max_length=120)
    ruc_institucion: Optional[str] = Field(default=None, pattern=r"^\d{11}$")
    tipo_institucion: Optional[str] = Field(default=None, min_length=2, max_length=60)
    region_institucion: Optional[str] = Field(default=None, min_length=2, max_length=100)
    correo_institucional: Optional[str] = Field(default=None, min_length=5, max_length=200)
    contacto_institucional: Optional[str] = Field(default=None, min_length=2, max_length=120)
    telefono_institucional: Optional[str] = Field(default=None, min_length=6, max_length=40)
    evidencia_institucional_url: Optional[str] = Field(default=None, min_length=8, max_length=500)
    rol: str = Field(default="ciudadano")
    institucion: str = Field(default="individual", max_length=120)

class AuthResponse(BaseModel):
    mensaje: str
    usuario: str
    rol: str
    institucion: str = "individual"
    permisos: List[str] = []
    token: Optional[str] = None
    codigo_enlace: Optional[str] = None
