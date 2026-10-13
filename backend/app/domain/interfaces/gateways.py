from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class INotificationGateway(ABC):
    """Contrato para despacho de alertas a familiares y centros de emergencia."""

    @abstractmethod
    def notify_family_members(
        self,
        familiares: List[str],
        tipo_emergencia: str,
        coordenadas: Dict[str, float],
        es_critico: bool
    ) -> Dict[str, Any]:
        """Envía notificaciones de emergencia (SMS / Push) a la red de protección."""
        pass

    @abstractmethod
    def dispatch_institutional_alert(
        self,
        institucion: str,
        alerta_id: int,
        tipo_emergencia: str,
        prioridad: int,
        coordenadas: Dict[str, float]
    ) -> Dict[str, Any]:
        """Despacha la alerta al Centro de Operaciones (COER / Bomberos / PNP)."""
        pass


class IRoutingGateway(ABC):
    """Contrato para cálculo de rutas terrestres de rescate y evasión de vías bloqueadas."""

    @abstractmethod
    def compute_rescue_route(
        self,
        origen_lat: float,
        origen_lng: float,
        destino_lat: float,
        destino_lng: float,
        evitar_bloqueos: bool = False
    ) -> Dict[str, Any]:
        pass


class ICAPGateway(ABC):
    """Contrato para exportación al estándar Common Alerting Protocol (OASIS CAP v1.2)."""

    @abstractmethod
    def format_as_cap_payload(
        self,
        alerta_id: int,
        tipo_emergencia: str,
        gravedad: int,
        lat: float,
        lng: float,
        descripcion: str,
        origen: str
    ) -> Dict[str, Any]:
        pass


class ISMSGateway(ABC):
    """Canal desacoplado para envío SMS y autenticación de webhooks entrantes."""

    @abstractmethod
    def enviar(self, destinatario: str, mensaje: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validar_firma_webhook(
        self,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        content_type: str,
    ) -> bool:
        pass
