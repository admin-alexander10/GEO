import re
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

TipoPunto = Literal["COMISARIA", "BOMBEROS", "SALUD", "SERENAZGO", "OTRO"]
TIPOS_PUNTO = ("COMISARIA", "BOMBEROS", "SALUD", "SERENAZGO", "OTRO")
_TELEFONO = re.compile(r"^[+(]?[0-9][0-9 ()\-]{1,38}$")


def normalizar_telefono(valor: Optional[str]) -> Optional[str]:
    """Devuelve el teléfono limpio, None si viene vacío, o lanza ValueError si no parece un teléfono."""
    if valor is None:
        return None
    telefono = " ".join(str(valor).split())
    if not telefono:
        return None
    if not _TELEFONO.fullmatch(telefono) or sum(caracter.isdigit() for caracter in telefono) < 3:
        raise ValueError("El teléfono solo puede tener dígitos, espacios, guiones, paréntesis y un + inicial.")
    return telefono


class PuntoPublico(BaseModel):
    """Lo que recibe la app: lo mínimo para mostrar el punto más cercano y llamarlo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    nombre: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    distrito: Optional[str] = None
    latitud: float
    longitud: float
    ubicacion_aproximada: bool = False
    verificado_en: date


class DirectorioPublico(BaseModel):
    version: str
    # True cuando el cliente ya tiene esta versión: `puntos` llega vacío y debe conservar su copia.
    sin_cambios: bool = False
    total: int
    puntos: List[PuntoPublico] = Field(default_factory=list)


class PuntoAdmin(PuntoPublico):
    fuente: str
    activo: bool
    actualizado_en: datetime


class PuntoCrear(BaseModel):
    tipo: TipoPunto
    nombre: str = Field(..., min_length=3, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=40)
    direccion: Optional[str] = Field(default=None, max_length=300)
    distrito: Optional[str] = Field(default=None, max_length=120)
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    ubicacion_aproximada: bool = False
    # De dónde salió el dato y cuándo lo comprobó quien lo registra.
    fuente: str = Field(..., min_length=10, max_length=1000)
    verificado_en: date

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: Optional[str]) -> Optional[str]:
        return normalizar_telefono(value)

    @field_validator("nombre", "fuente")
    @classmethod
    def limpiar_texto(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("direccion", "distrito")
    @classmethod
    def limpiar_opcional(cls, value: Optional[str]) -> Optional[str]:
        limpio = " ".join(value.split()) if value else ""
        return limpio or None

    @field_validator("verificado_en")
    @classmethod
    def fecha_no_futura(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La fecha de verificación no puede ser futura.")
        return value


class PuntoActualizar(BaseModel):
    """Corrección de una entrada. Cambiar el teléfono exige declarar de nuevo fuente y fecha."""
    telefono: Optional[str] = Field(default=None, max_length=40)
    activo: Optional[bool] = None
    fuente: Optional[str] = Field(default=None, min_length=10, max_length=1000)
    verificado_en: Optional[date] = None

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: Optional[str]) -> Optional[str]:
        return normalizar_telefono(value)


class ImportacionRequest(BaseModel):
    csv: str = Field(..., min_length=10, max_length=3_000_000)
    fuente: str = Field(..., min_length=10, max_length=1000)
    verificado_en: date
    # Para archivos de un solo tipo que no traen la columna `tipo`.
    tipo_por_defecto: Optional[TipoPunto] = None

    @field_validator("verificado_en")
    @classmethod
    def fecha_no_futura(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La fecha de verificación no puede ser futura.")
        return value


class FilaRechazada(BaseModel):
    fila: int
    motivo: str


class ImportacionResponse(BaseModel):
    creados: int
    actualizados: int
    sin_telefono: int
    con_ubicacion_aproximada: int = 0
    rechazados: List[FilaRechazada]
    total_rechazados: int
    columnas_detectadas: List[str]


class ResumenDirectorio(BaseModel):
    total_activos: int
    por_tipo: dict
    sin_telefono: int
    verificacion_mas_antigua: Optional[date] = None
