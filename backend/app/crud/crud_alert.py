# Wrapper de compatibilidad hacia atrás
from sqlalchemy.orm import Session
from typing import List
from app.models.alert import AlertaEmergencia
from app.schemas.alert import AlertaCreate, AlertaDetalle
from app.repositories.alert_repository import AlertRepository

def create_alert(db: Session, alerta_in: AlertaCreate) -> AlertaEmergencia:
    repo = AlertRepository(db)
    return repo.create_spatial_alert(
        dispositivo_id=getattr(alerta_in, 'dispositivo_id', 'DEV_GENERIC'),
        tipo_emergencia=alerta_in.tipo_emergencia,
        nivel_gravedad=alerta_in.nivel_gravedad,
        latitud=alerta_in.latitud,
        longitud=alerta_in.longitud,
        usuario=getattr(alerta_in, 'usuario', None)
    )

def get_active_alerts(db: Session, limit: int = 50) -> List[AlertaDetalle]:
    repo = AlertRepository(db)
    query_result = repo.get_active_alerts_with_coords(limit=limit)
    alertas = []
    for alerta, lat, lng in query_result:
        es_critico = (alerta.nivel_gravedad or 3) >= 4
        alertas.append(AlertaDetalle(
            id=alerta.id,
            dispositivo_id=alerta.dispositivo_id,
            usuario=alerta.dispositivo_id,
            tipo_emergencia=alerta.tipo_emergencia,
            nivel_gravedad=alerta.nivel_gravedad or 3,
            origen_alerta="AUTOMATICO_INERCIA" if es_critico else "MANUAL",
            estado_confirmacion="EXPIRADO_INCONSCIENTE" if es_critico else "CONFIRMADO",
            latitud=float(lat),
            longitud=float(lng),
            timestamp_dispositivo=alerta.timestamp_dispositivo,
            creado_en=alerta.creado_en
        ))
    return alertas
