from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.alert import AlertaEmergencia
from app.services.base_service import BaseService
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import (
    AlertaCreate,
    AlertaResponse,
    AlertaDetalle,
    AlertStateUpdate,
    AlertaSinAsignar,
    AsignacionManualResponse,
    EnrutamientoInstitucional,
    NotificacionFamiliar,
)

class AlertService(BaseService):
    """
    Servicio de orquestación de emergencias y despacho táctico:
    1. Persiste el punto espacial en PostgreSQL con PostGIS.
    2. Identifica la red familiar del usuario y despacha notificaciones.
    3. Asigna recursos de respuesta B2G (COER / Bomberos).
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.alert_repo = AlertRepository(db)

    def despachar_alerta(self, alerta_in: AlertaCreate, canal_entrada: str = "API") -> AlertaResponse:
        # 1. Persistencia geoespacial en PostGIS
        alerta_db = self.alert_repo.create_spatial_alert(
            dispositivo_id=alerta_in.dispositivo_id or alerta_in.usuario or "DEV_GENERIC",
            tipo_emergencia=alerta_in.tipo_emergencia,
            nivel_gravedad=alerta_in.nivel_gravedad,
            latitud=alerta_in.latitud,
            longitud=alerta_in.longitud,
            usuario=alerta_in.usuario,
            origen_alerta=alerta_in.origen_alerta,
            estado_confirmacion=alerta_in.estado_confirmacion,
            client_alert_id=alerta_in.client_alert_id,
            canal_entrada=canal_entrada,
            precision_m=alerta_in.precision_m,
            edad_lectura_s=alerta_in.edad_lectura_s,
            es_simulacro=alerta_in.es_simulacro,
            timestamp_dispositivo=alerta_in.timestamp_dispositivo,
        )

        recipient_count = self.alert_repo.count_family_recipients(alerta_db.id)
        instituciones = list(self.alert_repo.get_institution_recipients(alerta_db.id))
        return AlertaResponse(
            estado=alerta_db.estado,
            alerta_id=alerta_db.id,
            client_alert_id=alerta_db.client_alert_id,
            origen=alerta_db.origen_alerta,
            confirmacion=alerta_db.estado_confirmacion,
            coordenadas=(
                {"lat": alerta_in.latitud, "lng": alerta_in.longitud}
                if alerta_in.latitud is not None and alerta_in.longitud is not None
                else None
            ),
            enrutamiento_institucional=EnrutamientoInstitucional(
                estado="EN_BANDEJA_INSTITUCIONAL" if instituciones else "SIN_COBERTURA_CONFIRMADA",
                institucion_responsable=", ".join(instituciones) or None,
                instituciones=instituciones,
                prioridad=alerta_in.nivel_gravedad,
            ),
            notificacion_familiar=NotificacionFamiliar(
                estado="DISPONIBLE_EN_BUZON" if recipient_count else "SIN_VINCULOS_CON_CONSENTIMIENTO",
            ),
            creado_en=alerta_db.creado_en,
        )

    def actualizar_ubicacion_sms(
        self,
        client_alert_id: str,
        usuario: str,
        latitud: float,
        longitud: float,
        precision_m: int,
        edad_lectura_s: int,
    ) -> AlertaEmergencia:
        return self.alert_repo.update_sms_location(
            client_alert_id=client_alert_id,
            usuario=usuario,
            latitud=latitud,
            longitud=longitud,
            precision_m=precision_m,
            edad_lectura_s=edad_lectura_s,
        )

    def cancelar_alerta_sms(
        self,
        client_alert_id: str,
        usuario: str,
        actor: str,
    ) -> AlertaEmergencia:
        alerta_existente = self.alert_repo.get_alert_by_client_id_for_user(
            client_alert_id=client_alert_id,
            usuario=usuario,
        )
        if alerta_existente and alerta_existente.estado == "CANCELADA":
            return alerta_existente
        return self.alert_repo.cancel_sms_alert(
            client_alert_id=client_alert_id,
            usuario=usuario,
            actor=actor,
        )

    def instituciones_asignadas(self, alerta_id: int) -> List[str]:
        return list(self.alert_repo.get_institution_recipients(alerta_id))

    def listar_sin_asignar(self, limit: int = 50) -> List[AlertaSinAsignar]:
        return [
            AlertaSinAsignar(
                id=alerta.id,
                usuario=alerta.usuario,
                tipo_emergencia=alerta.tipo_emergencia,
                nivel_gravedad=alerta.nivel_gravedad,
                origen_alerta=alerta.origen_alerta,
                estado=alerta.estado,
                canal_entrada=alerta.canal_entrada,
                latitud=alerta.latitud,
                longitud=alerta.longitud,
                creado_en=alerta.creado_en,
                instituciones_en_cobertura=self.alert_repo.institutions_covering(alerta.latitud, alerta.longitud),
            )
            for alerta in self.alert_repo.get_unassigned_open_alerts(limit=limit)
        ]

    def asignar_manualmente(self, alerta_id: int, institution_name: str, actor: str, reason: str) -> AsignacionManualResponse:
        alerta = self.alert_repo.assign_alert_manually(
            alert_id=alerta_id,
            institution_name=institution_name,
            actor=actor,
            reason=reason,
        )
        return AsignacionManualResponse(
            alerta_id=alerta.id,
            estado=alerta.estado,
            instituciones=self.instituciones_asignadas(alerta.id),
        )

    def listar_alertas_activas(self, institucion: Optional[str], limit: int = 50) -> List[AlertaDetalle]:
        """Lista únicamente alertas asignadas a la institución autenticada."""
        query_result = self.alert_repo.get_institution_alerts_with_coords(
            institution_name=institucion,
            limit=limit,
        )
        return self._map_alertas(query_result)

    def listar_buzon_familiar(self, usuario: str, limit: int = 50) -> List[AlertaDetalle]:
        query_result = self.alert_repo.get_family_alerts_with_coords(username=usuario, limit=limit)
        return self._map_alertas(query_result)

    def cambiar_estado(
        self,
        alerta_id: int,
        usuario: str,
        rol: str,
        institucion: Optional[str],
        cambio: AlertStateUpdate,
    ) -> AlertaDetalle:
        alerta = self.alert_repo.transition_alert(
            alert_id=alerta_id,
            actor=usuario,
            actor_role=rol,
            institution=institucion,
            new_state=cambio.estado,
            reason=cambio.motivo,
        )
        latitud, longitud = self.alert_repo.get_alert_coordinates(alerta.id)
        return AlertaDetalle(
            id=alerta.id,
            dispositivo_id=alerta.dispositivo_id,
            usuario=alerta.usuario,
            tipo_emergencia=alerta.tipo_emergencia,
            nivel_gravedad=alerta.nivel_gravedad,
            origen_alerta=alerta.origen_alerta,
            estado_confirmacion=alerta.estado_confirmacion,
            estado=alerta.estado,
            client_alert_id=alerta.client_alert_id,
            canal_entrada=alerta.canal_entrada,
            precision_m=alerta.precision_m,
            edad_lectura_s=alerta.edad_lectura_s,
            es_simulacro=alerta.es_simulacro,
            latitud=latitud,
            longitud=longitud,
            timestamp_dispositivo=alerta.timestamp_dispositivo,
            creado_en=alerta.creado_en,
        )

    @staticmethod
    def _map_alertas(query_result) -> List[AlertaDetalle]:
        alertas: List[AlertaDetalle] = []

        for alerta, lat, lng in query_result:
            alertas.append(AlertaDetalle(
                id=alerta.id,
                dispositivo_id=alerta.dispositivo_id,
                usuario=alerta.usuario,
                tipo_emergencia=alerta.tipo_emergencia,
                nivel_gravedad=alerta.nivel_gravedad or 3,
                origen_alerta=alerta.origen_alerta,
                estado_confirmacion=alerta.estado_confirmacion,
                estado=alerta.estado,
                client_alert_id=alerta.client_alert_id,
                canal_entrada=alerta.canal_entrada,
                precision_m=alerta.precision_m,
                edad_lectura_s=alerta.edad_lectura_s,
                es_simulacro=alerta.es_simulacro,
                latitud=float(lat) if lat is not None else None,
                longitud=float(lng) if lng is not None else None,
                timestamp_dispositivo=alerta.timestamp_dispositivo,
                creado_en=alerta.creado_en
            ))
        return alertas
