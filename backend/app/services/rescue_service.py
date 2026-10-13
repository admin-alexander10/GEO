from typing import Dict, Any
from app.infrastructure.gateways.routing_gateway import EmergencyRoutingGateway
from app.schemas.rescue import RutaRequest, RutaResponse

class RescueService:
    """Servicio de operaciones tácticas de rescate y enrutamiento con evasión de bloqueos."""

    def __init__(self):
        self.routing_gateway = EmergencyRoutingGateway()

    def calcular_ruta_rescate(self, ruta_in: RutaRequest) -> RutaResponse:
        resultado = self.routing_gateway.compute_rescue_route(
            origen_lat=ruta_in.origen_lat,
            origen_lng=ruta_in.origen_lng,
            destino_lat=ruta_in.destino_lat,
            destino_lng=ruta_in.destino_lng,
            evitar_bloqueos=ruta_in.bloqueos_detectados
        )

        return RutaResponse(
            origen={"lat": ruta_in.origen_lat, "lng": ruta_in.origen_lng},
            destino={"lat": ruta_in.destino_lat, "lng": ruta_in.destino_lng},
            bloqueos_evitados=resultado["bloqueos_evitados"],
            distancia_km=resultado["distancia_km"],
            tiempo_estimado_llegada=resultado["tiempo_estimado"],
            estado_algoritmo=resultado["estado_algoritmo"],
            puntos_ruta=resultado["puntos_ruta"]
        )
