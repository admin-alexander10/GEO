from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from geoalchemy2 import Geometry
from datetime import datetime
from app.db.base import Base


class AlertaEmergencia(Base):
    __tablename__ = "alertas_emergencia"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_alert_id = Column(String(36), nullable=True, unique=True)
    dispositivo_id = Column(String(100), index=True, nullable=False)
    usuario = Column(String(100), index=True, nullable=True)
    tipo_emergencia = Column(String(150), nullable=False)
    nivel_gravedad = Column(Integer, nullable=True)
    origen_alerta = Column(String(50), default="MANUAL", nullable=False)
    estado_confirmacion = Column(String(50), default="CONFIRMADO", nullable=False)
    estado = Column(String(40), default="REGISTRADA", nullable=False)
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)
    canal_entrada = Column(String(20), default="API", nullable=False)
    precision_m = Column(Integer, nullable=True)
    edad_lectura_s = Column(Integer, nullable=True)
    es_simulacro = Column(Boolean, default=False, nullable=False)
    ubicacion = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    timestamp_dispositivo = Column(DateTime, default=datetime.utcnow, nullable=False)
    sincronizado = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class AlertStateHistory(Base):
    __tablename__ = "alert_state_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(
        Integer,
        ForeignKey("alertas_emergencia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor = Column(String(100), nullable=False)
    from_state = Column(String(40), nullable=True)
    to_state = Column(String(40), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reason = Column(Text, nullable=True)


class AlertOutbox(Base):
    __tablename__ = "alert_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(
        Integer,
        ForeignKey("alertas_emergencia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(80), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    available_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)


class AlertRecipient(Base):
    __tablename__ = "alert_recipients"
    __table_args__ = (
        UniqueConstraint(
            "alert_id",
            "recipient_type",
            "recipient_username",
            name="uq_alert_recipient",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(
        Integer,
        ForeignKey("alertas_emergencia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recipient_type = Column(String(20), nullable=False)
    recipient_username = Column(String(100), nullable=False, index=True)
    available_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)
