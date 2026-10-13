import json
from typing import List, Optional, Tuple, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from geoalchemy2.elements import WKTElement
from app.repositories.base_repository import BaseRepository
from app.domain.interfaces.repositories import IAlertRepository
from app.domain.exceptions import (
    EntityNotFoundException,
    ForbiddenException,
    IdempotencyConflictException,
)
from app.models.alert import AlertOutbox, AlertRecipient, AlertStateHistory, AlertaEmergencia
from app.models.family import RedFamiliar
from app.models.subscription import InstitutionAccount
from app.models.user import Usuario
from app.core.config import settings
from app.core.geo import distancia_km
from app.domain.enums import EstadoConfirmacion

class AlertRepository(BaseRepository[AlertaEmergencia], IAlertRepository):
    """Repositorio geoespacial especializado en PostgreSQL / PostGIS."""

    ESTADOS_ABIERTOS = ("REGISTRADA", "RECIBIDA", "EN_ATENCION")

    def __init__(self, db: Session):
        super().__init__(db, AlertaEmergencia)

    # ------------------------------------------------------------------
    # Asignación institucional por cobertura validada
    # ------------------------------------------------------------------
    def institutions_covering(self, latitud: Optional[float], longitud: Optional[float]) -> List[str]:
        """Instituciones activas cuya cobertura validada contiene el punto.

        La cobertura es un círculo (centro + radio) que el propietario de la
        plataforma registró y validó. Sin ubicación o sin cobertura validada no
        se asigna nada: nunca se usa una institución predeterminada.
        """
        if latitud is None or longitud is None:
            return []
        candidatas = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.is_active.is_(True),
            InstitutionAccount.coverage_validated_at.is_not(None),
        ).all()
        nombres = []
        for institucion in candidatas:
            if (
                institucion.coverage_lat is None
                or institucion.coverage_lng is None
                or institucion.coverage_radius_km is None
            ):
                continue
            distancia = distancia_km(latitud, longitud, institucion.coverage_lat, institucion.coverage_lng)
            if distancia <= institucion.coverage_radius_km:
                nombres.append(institucion.institution_name)
        return sorted(nombres)

    def _add_institution_recipients(self, alert_id: int, nombres: List[str], ahora: datetime) -> List[str]:
        """Agrega a la bandeja las instituciones que aún no tengan la alerta."""
        if not nombres:
            return []
        ya_asignadas = {
            fila.recipient_username
            for fila in self.db.query(AlertRecipient).filter(
                AlertRecipient.alert_id == alert_id,
                AlertRecipient.recipient_type == "INSTITUTION",
            ).all()
        }
        nuevas = [nombre for nombre in nombres if nombre not in ya_asignadas]
        for nombre in nuevas:
            self.db.add(AlertRecipient(
                alert_id=alert_id,
                recipient_type="INSTITUTION",
                recipient_username=nombre,
                available_at=ahora,
            ))
        return nuevas

    def _lock_security_email(self, usuario: Optional[str], ahora: datetime) -> None:
        """Desde una alerta real, el correo de seguridad no se puede cambiar por un tiempo."""
        if not usuario:
            return
        cuenta = self.db.query(Usuario).filter(Usuario.usuario == usuario).first()
        if cuenta is not None:
            cuenta.correo_seguridad_bloqueado_hasta = ahora + timedelta(hours=settings.SECURITY_EMAIL_LOCK_HOURS)

    def get_institution_recipients(self, alert_id: int) -> List[str]:
        filas = self.db.query(AlertRecipient).filter(
            AlertRecipient.alert_id == alert_id,
            AlertRecipient.recipient_type == "INSTITUTION",
        ).all()
        return sorted(fila.recipient_username for fila in filas)

    @staticmethod
    def _matches_request(
        existing: AlertaEmergencia,
        usuario: Optional[str],
        tipo_emergencia: str,
        nivel_gravedad: int,
        latitud: Optional[float],
        longitud: Optional[float],
        origen_alerta: str,
        estado_confirmacion: str,
    ) -> bool:
        return (
            existing.usuario == usuario
            and existing.tipo_emergencia == tipo_emergencia
            and existing.nivel_gravedad == nivel_gravedad
            and existing.latitud == latitud
            and existing.longitud == longitud
            and existing.origen_alerta == origen_alerta
            and existing.estado_confirmacion == estado_confirmacion
        )

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
        timestamp_dispositivo: Optional[datetime] = None,
    ) -> AlertaEmergencia:
        """Inserta punto espacial POINT(longitud latitud) en SRID 4326."""
        if client_alert_id:
            existente = self.db.query(AlertaEmergencia).filter(
                AlertaEmergencia.client_alert_id == client_alert_id
            ).first()
            if existente:
                if not self._matches_request(
                    existente,
                    usuario,
                    tipo_emergencia,
                    nivel_gravedad,
                    latitud,
                    longitud,
                    origen_alerta,
                    estado_confirmacion,
                ):
                    raise IdempotencyConflictException()
                return existente

        if (latitud is None) != (longitud is None):
            raise ValueError("La latitud y la longitud deben enviarse juntas o ambas omitirse.")
        ubicacion_geo = (
            WKTElement(f"POINT({longitud} {latitud})", srid=4326)
            if latitud is not None and longitud is not None
            else None
        )
        ahora = datetime.utcnow()
        nueva_alerta = AlertaEmergencia(
            client_alert_id=client_alert_id,
            dispositivo_id=dispositivo_id,
            usuario=usuario,
            tipo_emergencia=tipo_emergencia,
            nivel_gravedad=nivel_gravedad,
            origen_alerta=origen_alerta,
            estado_confirmacion=estado_confirmacion,
            estado="REGISTRADA",
            latitud=latitud,
            longitud=longitud,
            ubicacion=ubicacion_geo,
            timestamp_dispositivo=timestamp_dispositivo or ahora,
            sincronizado=True,
            creado_en=ahora,
            canal_entrada=canal_entrada,
            precision_m=precision_m,
            edad_lectura_s=edad_lectura_s,
            es_simulacro=es_simulacro,
        )
        try:
            self.db.add(nueva_alerta)
            self.db.flush()
            self.db.add(AlertStateHistory(
                alert_id=nueva_alerta.id,
                actor=usuario or dispositivo_id,
                from_state=None,
                to_state="REGISTRADA",
                changed_at=ahora,
            ))
            links = self.db.query(RedFamiliar).filter(
                RedFamiliar.usuario_responsable == usuario,
                RedFamiliar.familiar_usuario.is_not(None),
                RedFamiliar.consentimiento_en.is_not(None),
                RedFamiliar.revocado_en.is_(None),
            ).all() if usuario else []
            for link in links:
                self.db.add(AlertRecipient(
                    alert_id=nueva_alerta.id,
                    recipient_type="FAMILY",
                    recipient_username=link.familiar_usuario,
                    available_at=ahora,
                ))
            if not es_simulacro:
                self._add_institution_recipients(
                    nueva_alerta.id,
                    self.institutions_covering(latitud, longitud),
                    ahora,
                )
                self._lock_security_email(usuario, ahora)
            self.db.add(AlertOutbox(
                alert_id=nueva_alerta.id,
                event_type="alert.created",
                payload=json.dumps({"alert_id": nueva_alerta.id}),
                status="PENDING",
                attempts=0,
                available_at=ahora,
                created_at=ahora,
            ))
            self.db.commit()
            self.db.refresh(nueva_alerta)
            return nueva_alerta
        except IntegrityError:
            self.db.rollback()
            if client_alert_id:
                existente = self.db.query(AlertaEmergencia).filter(
                    AlertaEmergencia.client_alert_id == client_alert_id
                ).first()
                if existente:
                    if not self._matches_request(
                        existente,
                        usuario,
                        tipo_emergencia,
                        nivel_gravedad,
                        latitud,
                        longitud,
                        origen_alerta,
                        estado_confirmacion,
                    ):
                        raise IdempotencyConflictException()
                    return existente
            raise
        except Exception:
            self.db.rollback()
            raise

    def get_alert_by_client_id_for_user(
        self,
        client_alert_id: str,
        usuario: str,
    ) -> Optional[AlertaEmergencia]:
        return self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.client_alert_id == client_alert_id,
            AlertaEmergencia.usuario == usuario,
        ).first()

    def update_sms_location(
        self,
        client_alert_id: str,
        usuario: str,
        latitud: float,
        longitud: float,
        precision_m: int,
        edad_lectura_s: int,
    ) -> AlertaEmergencia:
        alerta = self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.client_alert_id == client_alert_id,
            AlertaEmergencia.usuario == usuario,
        ).with_for_update().first()
        if not alerta:
            raise EntityNotFoundException("Alerta", client_alert_id)
        if alerta.estado not in self.ESTADOS_ABIERTOS:
            raise ForbiddenException("La alerta ya no está abierta para actualizar su ubicación.")
        alerta.latitud = latitud
        alerta.longitud = longitud
        alerta.ubicacion = WKTElement(f"POINT({longitud} {latitud})", srid=4326)
        alerta.precision_m = precision_m
        alerta.edad_lectura_s = edad_lectura_s
        self.db.add(alerta)
        if not alerta.es_simulacro:
            # La nueva posición puede caer en la cobertura de otra institución.
            # Las asignaciones previas se conservan: ya pudieron ser vistas.
            self._add_institution_recipients(
                alerta.id,
                self.institutions_covering(latitud, longitud),
                datetime.utcnow(),
            )
        self.db.commit()
        self.db.refresh(alerta)
        return alerta

    def cancel_sms_alert(
        self,
        client_alert_id: str,
        usuario: str,
        actor: str,
    ) -> AlertaEmergencia:
        alerta = self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.client_alert_id == client_alert_id,
            AlertaEmergencia.usuario == usuario,
        ).with_for_update().first()
        if not alerta:
            raise EntityNotFoundException("Alerta", client_alert_id)
        if alerta.estado != "REGISTRADA":
            raise ForbiddenException("Solo se puede cancelar una alerta aún no recibida.")
        anterior = alerta.estado
        alerta.estado = "CANCELADA"
        alerta.estado_confirmacion = EstadoConfirmacion.CANCELADO_USUARIO.value
        self.db.add(alerta)
        self.db.add(AlertStateHistory(
            alert_id=alerta.id,
            actor=actor,
            from_state=anterior,
            to_state=alerta.estado,
            changed_at=datetime.utcnow(),
            reason="Cancelación recibida por SMS firmado.",
        ))
        self.db.commit()
        self.db.refresh(alerta)
        return alerta

    def count_family_recipients(self, alert_id: int) -> int:
        return self.db.query(AlertRecipient).filter(
            AlertRecipient.alert_id == alert_id,
            AlertRecipient.recipient_type == "FAMILY",
        ).count()

    def get_alert_coordinates(self, alert_id: int) -> Tuple[Optional[float], Optional[float]]:
        result = self.db.query(
            func.ST_Y(AlertaEmergencia.ubicacion),
            func.ST_X(AlertaEmergencia.ubicacion),
        ).filter(AlertaEmergencia.id == alert_id).first()
        if not result:
            return None, None
        latitud, longitud = result
        return (
            float(latitud) if latitud is not None else None,
            float(longitud) if longitud is not None else None,
        )

    def get_family_alerts_with_coords(
        self,
        username: str,
        limit: int = 50,
    ) -> List[Tuple[AlertaEmergencia, Optional[float], Optional[float]]]:
        return self.db.query(
            AlertaEmergencia,
            func.ST_Y(AlertaEmergencia.ubicacion).label("latitud"),
            func.ST_X(AlertaEmergencia.ubicacion).label("longitud"),
        ).join(
            AlertRecipient,
            AlertRecipient.alert_id == AlertaEmergencia.id,
        ).join(
            RedFamiliar,
            (RedFamiliar.usuario_responsable == AlertaEmergencia.usuario)
            & (RedFamiliar.familiar_usuario == AlertRecipient.recipient_username),
        ).filter(
            AlertRecipient.recipient_username == username,
            AlertRecipient.recipient_type == "FAMILY",
            RedFamiliar.consentimiento_en.is_not(None),
            RedFamiliar.revocado_en.is_(None),
            AlertaEmergencia.estado.in_(self.ESTADOS_ABIERTOS),
        ).order_by(AlertaEmergencia.id.desc()).limit(limit).all()

    def get_institution_alerts_with_coords(
        self,
        institution_name: Optional[str],
        limit: int = 50,
    ) -> List[Tuple[AlertaEmergencia, Optional[float], Optional[float]]]:
        if not institution_name:
            return []
        return self.db.query(
            AlertaEmergencia,
            func.ST_Y(AlertaEmergencia.ubicacion).label("latitud"),
            func.ST_X(AlertaEmergencia.ubicacion).label("longitud"),
        ).join(
            AlertRecipient,
            AlertRecipient.alert_id == AlertaEmergencia.id,
        ).filter(
            AlertRecipient.recipient_username == institution_name,
            AlertRecipient.recipient_type == "INSTITUTION",
            AlertaEmergencia.estado.in_(self.ESTADOS_ABIERTOS),
        ).order_by(AlertaEmergencia.id.desc()).limit(limit).all()

    def get_unassigned_open_alerts(self, limit: int = 50) -> List[AlertaEmergencia]:
        """Alertas reales y abiertas que ninguna institución tiene en su bandeja."""
        tiene_institucion = exists().where(
            AlertRecipient.alert_id == AlertaEmergencia.id,
            AlertRecipient.recipient_type == "INSTITUTION",
        )
        return self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.estado.in_(self.ESTADOS_ABIERTOS),
            AlertaEmergencia.es_simulacro.is_(False),
            ~tiene_institucion,
        ).order_by(AlertaEmergencia.id.desc()).limit(limit).all()

    def assign_alert_manually(
        self,
        alert_id: int,
        institution_name: str,
        actor: str,
        reason: str,
    ) -> AlertaEmergencia:
        """Asignación manual por el propietario; queda auditada en el historial."""
        alerta = self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.id == alert_id
        ).with_for_update().first()
        if not alerta:
            raise EntityNotFoundException("Alerta", str(alert_id))
        if alerta.estado not in self.ESTADOS_ABIERTOS:
            raise ForbiddenException("La alerta ya está cerrada y no se puede asignar.")
        if alerta.es_simulacro:
            raise ForbiddenException("Un simulacro no se asigna a instituciones.")
        institucion = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution_name,
            InstitutionAccount.is_active.is_(True),
        ).first()
        if not institucion:
            raise EntityNotFoundException("Institución activa", institution_name)
        ahora = datetime.utcnow()
        nuevas = self._add_institution_recipients(alerta.id, [institution_name], ahora)
        if nuevas:
            self.db.add(AlertStateHistory(
                alert_id=alerta.id,
                actor=actor,
                from_state=alerta.estado,
                to_state=alerta.estado,
                changed_at=ahora,
                reason=f"Asignación manual a {institution_name}: {reason}",
            ))
        self.db.commit()
        self.db.refresh(alerta)
        return alerta

    def transition_alert(
        self,
        alert_id: int,
        actor: str,
        actor_role: str,
        institution: Optional[str],
        new_state: str,
        reason: Optional[str] = None,
    ) -> AlertaEmergencia:
        alerta = self.db.query(AlertaEmergencia).filter(
            AlertaEmergencia.id == alert_id
        ).with_for_update().first()
        if not alerta:
            raise EntityNotFoundException("Alerta", str(alert_id))

        if actor_role == "ciudadano":
            if alerta.usuario != actor or alerta.estado != "REGISTRADA" or new_state != "CANCELADA":
                raise ForbiddenException("Solo puedes cancelar tu propia alerta aún no recibida.")
        else:
            asignacion = self.db.query(AlertRecipient).filter(
                AlertRecipient.alert_id == alert_id,
                AlertRecipient.recipient_type == "INSTITUTION",
                AlertRecipient.recipient_username == institution,
            ).first()
            transitions = {
                "REGISTRADA": {"RECIBIDA"},
                "RECIBIDA": {"EN_ATENCION", "RESUELTA"},
                "EN_ATENCION": {"ATENDIDA", "RESUELTA"},
            }
            if not asignacion or new_state not in transitions.get(alerta.estado, set()):
                raise ForbiddenException("La institución no tiene asignada esta alerta o la transición no es válida.")

        anterior = alerta.estado
        alerta.estado = new_state
        self.db.add(alerta)
        self.db.add(AlertStateHistory(
            alert_id=alerta.id,
            actor=actor,
            from_state=anterior,
            to_state=new_state,
            changed_at=datetime.utcnow(),
            reason=reason,
        ))
        self.db.commit()
        self.db.refresh(alerta)
        return alerta

    def get_active_alerts_with_coords(self, limit: int = 50) -> List[Tuple[AlertaEmergencia, float, float]]:
        """Extrae la entidad junto con latitud y longitud calculadas por PostGIS (ST_Y, ST_X)."""
        return self.db.query(
            AlertaEmergencia,
            func.ST_Y(AlertaEmergencia.ubicacion).label('latitud'),
            func.ST_X(AlertaEmergencia.ubicacion).label('longitud')
        ).order_by(AlertaEmergencia.id.desc()).limit(limit).all()

    def get_active_alerts(self, limit: int = 50) -> List[Any]:
        return self.get_active_alerts_with_coords(limit=limit)

    def get_alerts_in_radius(self, lat: float, lng: float, radius_km: float) -> List[Tuple[AlertaEmergencia, float, float]]:
        """Consulta geoespacial de proximidad usando buffer PostGIS."""
        punto_centro = WKTElement(f"POINT({lng} {lat})", srid=4326)
        # ST_DWithin con cast a geografía para distancia en metros
        return self.db.query(
            AlertaEmergencia,
            func.ST_Y(AlertaEmergencia.ubicacion).label('latitud'),
            func.ST_X(AlertaEmergencia.ubicacion).label('longitud')
        ).filter(
            func.ST_DWithin(
                func.cast(AlertaEmergencia.ubicacion, func.Geometry),
                punto_centro,
                radius_km / 111.32 # Aproximación en grados
            )
        ).order_by(AlertaEmergencia.id.desc()).all()
