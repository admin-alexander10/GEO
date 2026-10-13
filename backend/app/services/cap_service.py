from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.base_service import BaseService
from app.repositories.alert_repository import AlertRepository
from app.infrastructure.gateways.cap_gateway import OASISCAPGateway
from app.domain.exceptions import EntityNotFoundException

class CAPService(BaseService):
    """Servicio de interoperabilidad con el estándar internacional Common Alerting Protocol (CAP v1.2)."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.alert_repo = AlertRepository(db)
        self.cap_gateway = OASISCAPGateway()

    def exportar_alerta_cap(self, alerta_id: int) -> Dict[str, Any]:
        alertas_con_coords = self.alert_repo.get_active_alerts_with_coords(limit=500)
        encontrada = None
        for alerta, lat, lng in alertas_con_coords:
            if alerta.id == alerta_id:
                encontrada = (alerta, float(lat), float(lng))
                break

        if not encontrada:
            raise EntityNotFoundException("Alerta de Emergencia", str(alerta_id))

        alerta, lat, lng = encontrada
        return self.cap_gateway.format_as_cap_payload(
            alerta_id=alerta.id,
            tipo_emergencia=alerta.tipo_emergencia,
            gravedad=alerta.nivel_gravedad or 3,
            lat=lat,
            lng=lng,
            descripcion=f"Evento georreferenciado registrado en GEORESCUE IA para dispositivo {alerta.dispositivo_id}",
            origen="AUTOMATICO" if (alerta.nivel_gravedad or 0) >= 4 else "MANUAL"
        )
