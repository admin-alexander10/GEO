from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class RutaRequest(BaseModel):
    origen_lat: float
    origen_lng: float
    destino_lat: float
    destino_lng: float
    bloqueos_detectados: bool = Field(default=False)

class RutaResponse(BaseModel):
    origen: Dict[str, float]
    destino: Dict[str, float]
    bloqueos_evitados: Optional[bool] = None
    distancia_km: Optional[float] = None
    tiempo_estimado_llegada: Optional[str] = None
    estado_algoritmo: str
    puntos_ruta: List[List[float]] = Field(default_factory=list)
