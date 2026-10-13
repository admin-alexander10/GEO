from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Any

T = TypeVar("T")

class IBaseRepository(ABC, Generic[T]):
    """Contrato base para repositorios de persistencia."""
    
    @abstractmethod
    def get_by_id(self, id: Any) -> Optional[T]:
        pass

    @abstractmethod
    def list_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        pass

    @abstractmethod
    def create(self, entity: T) -> T:
        pass

    @abstractmethod
    def delete(self, id: Any) -> bool:
        pass


class IUserRepository(IBaseRepository[Any]):
    """Contrato para operaciones de persistencia de usuarios."""

    @abstractmethod
    def get_by_username(self, username: str) -> Optional[Any]:
        pass

    @abstractmethod
    def get_by_link_code(self, code: str) -> Optional[Any]:
        pass


class IAlertRepository(IBaseRepository[Any]):
    """Contrato para operaciones espaciales de alertas en PostGIS."""

    @abstractmethod
    def create_spatial_alert(
        self,
        dispositivo_id: str,
        tipo_emergencia: str,
        nivel_gravedad: int,
        latitud: Optional[float],
        longitud: Optional[float],
        usuario: Optional[str] = None,
        origen_alerta: str = "MANUAL",
        estado_confirmacion: str = "CONFIRMADO",
        client_alert_id: Optional[str] = None,
        canal_entrada: str = "API",
        precision_m: Optional[int] = None,
        edad_lectura_s: Optional[int] = None,
        es_simulacro: bool = False,
        timestamp_dispositivo: Any = None,
    ) -> Any:
        pass

    @abstractmethod
    def get_active_alerts(self, limit: int = 50) -> List[Any]:
        pass

    @abstractmethod
    def get_alerts_in_radius(self, lat: float, lng: float, radius_km: float) -> List[Any]:
        pass


class IFamilyRepository(IBaseRepository[Any]):
    """Contrato para la red de protección familiar."""

    @abstractmethod
    def get_by_responsible(self, usuario_responsable: str) -> List[Any]:
        pass

    @abstractmethod
    def create_consented_member(
        self,
        usuario_responsable: str,
        familiar_usuario: str,
        nombre: str,
        parentesco: str,
        consentimiento_en: Any,
    ) -> Any:
        pass
