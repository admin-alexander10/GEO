import logging
from typing import List, Dict, Any
from app.domain.interfaces.gateways import INotificationGateway

logger = logging.getLogger("georescue.notifications")


class EmergencyNotificationGateway(INotificationGateway):
    """Fallback de desarrollo que no simula entregas por canales externos."""

    def notify_family_members(
        self,
        familiares: List[str],
        tipo_emergencia: str,
        coordenadas: Dict[str, float],
        es_critico: bool
    ) -> Dict[str, Any]:
        logger.warning(
            "Notificación externa no configurada; alerta no despachada "
            "a familiares (cantidad solicitada: %s).",
            len(familiares),
        )
        return {
            "estado": "NO_CONFIGURADO",
            "familiares_alertados": [],
            "canal": None,
            "prioridad_alta": None,
        }

    def dispatch_institutional_alert(
        self,
        institucion: str,
        alerta_id: int,
        tipo_emergencia: str,
        prioridad: int,
        coordenadas: Dict[str, float]
    ) -> Dict[str, Any]:
        logger.warning(
            "Integración institucional no configurada; alerta %s no despachada.",
            alerta_id,
        )
        return {
            "estado": "SIN_COBERTURA_CONFIRMADA",
            "institucion_responsable": None,
            "prioridad": prioridad,
            "tiempo_estimado_despliegue": None,
            "canal_comunicacion": None,
        }
