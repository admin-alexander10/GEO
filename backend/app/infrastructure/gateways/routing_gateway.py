import logging
from typing import Dict, Any
from app.domain.interfaces.gateways import IRoutingGateway

logger = logging.getLogger("georescue.routing")


class EmergencyRoutingGateway(IRoutingGateway):
    """Fallback seguro: informa que no hay proveedor vial configurado."""

    def compute_rescue_route(
        self,
        origen_lat: float,
        origen_lng: float,
        destino_lat: float,
        destino_lng: float,
        evitar_bloqueos: bool = False
    ) -> Dict[str, Any]:
        logger.warning("Proveedor de rutas no configurado; no se calcula ruta ni ETA.")
        return {
            "distancia_km": None,
            "tiempo_estimado": None,
            "estado_algoritmo": "PROVEEDOR_DE_RUTAS_NO_CONFIGURADO",
            "bloqueos_evitados": None,
            "puntos_ruta": [],
        }
