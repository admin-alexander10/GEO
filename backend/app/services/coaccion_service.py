from datetime import datetime
from sqlalchemy.orm import Session
from app.services.base_service import BaseService
from app.repositories.alert_repository import AlertRepository
from app.schemas.coaccion import RoboCoaccionCreate, RoboCoaccionResponse

class CoaccionService(BaseService):
    """
    Servicio de protección silenciosa ante robo, asalto o coacción.
    Prioriza el despacho discreto hacia la Policía Nacional (PNP)
    y cifra el canal de aviso a familiares de confianza.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.alert_repo = AlertRepository(db)

    def despachar_robo_coaccion(self, alerta_in: RoboCoaccionCreate) -> RoboCoaccionResponse:
        coordenadas = None
        if alerta_in.latitud is not None and alerta_in.longitud is not None:
            coordenadas = {"lat": alerta_in.latitud, "lng": alerta_in.longitud}

        alerta_db = self.alert_repo.create_spatial_alert(
            dispositivo_id=alerta_in.dispositivo_id or alerta_in.usuario or "DEV_COACCION",
            tipo_emergencia="ROBO_ASALTO_COACCION",
            nivel_gravedad=alerta_in.nivel_gravedad,
            latitud=alerta_in.latitud,
            longitud=alerta_in.longitud,
            usuario=alerta_in.usuario,
            origen_alerta="PANIC_SILENCIOSO",
            estado_confirmacion="CONFIRMADO",
            client_alert_id=str(alerta_in.client_alert_id),
        )

        instituciones = list(self.alert_repo.get_institution_recipients(alerta_db.id))

        return RoboCoaccionResponse(
            estado=alerta_db.estado,
            alerta_id=alerta_db.id,
            client_alert_id=alerta_in.client_alert_id,
            tipo_emergencia="ROBO_ASALTO_COACCION",
            prioridad=alerta_in.nivel_gravedad,
            alerta_silenciosa=bool(alerta_in.activar_panic_silencioso or alerta_in.amenaza_detectada),
            coordenadas=coordenadas,
            enrutamiento_institucional={
                "prioridad": alerta_in.nivel_gravedad,
                "estado": "EN_BANDEJA_INSTITUCIONAL" if instituciones else "SIN_COBERTURA_CONFIRMADA",
                "institucion_responsible": ", ".join(instituciones) or None,
                "instituciones": instituciones,
                "tiempo_estimado_despliegue": None,
            },
            notificacion_familiar={
                "familiares_alertados": [],
                "estado": (
                    "DISPONIBLE_EN_BUZON"
                    if self.alert_repo.count_family_recipients(alerta_db.id)
                    else "SIN_VINCULOS_CON_CONSENTIMIENTO"
                ),
            },
            recurso_asignado=None,
        )
