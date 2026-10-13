from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.db.base import Base


class VerifiedPhone(Base):
    __tablename__ = "telefonos_verificados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(String(100), nullable=False, index=True)
    telefono = Column(String(20), nullable=False, unique=True, index=True)
    verificado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    activo = Column(Boolean, default=True, nullable=False, index=True)
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    ultimo_intento_fallido_en = Column(DateTime, nullable=True)


class PhoneOTPChallenge(Base):
    __tablename__ = "phone_otp_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(String(100), nullable=False, index=True)
    telefono = Column(String(20), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    salt = Column(String(32), nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    expira_en = Column(DateTime, nullable=False, index=True)
    intentos = Column(Integer, default=0, nullable=False)
    consumido_en = Column(DateTime, nullable=True)


class DeviceSigningKey(Base):
    __tablename__ = "dispositivos_firmantes"
    __table_args__ = (
        UniqueConstraint("usuario", "dispositivo_id", name="uq_dispositivo_firmante"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(String(100), nullable=False, index=True)
    dispositivo_id = Column(String(100), nullable=False)
    secreto_cifrado = Column(Text, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    revocado_en = Column(DateTime, nullable=True, index=True)


class DiscardedSMS(Base):
    __tablename__ = "sms_descartados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    remitente = Column(String(40), nullable=False, index=True)
    texto = Column(Text, nullable=False)
    motivo = Column(String(40), nullable=False, index=True)
    recibido_en = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SMSPhoneAbuseCounter(Base):
    __tablename__ = "sms_phone_abuse_counters"

    telefono = Column(String(40), primary_key=True)
    contador = Column(Integer, default=0, nullable=False)
    ultimo_motivo = Column(String(40), nullable=False)
    actualizado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class SMSOutboundRateLimit(Base):
    __tablename__ = "sms_outbound_rate_limits"

    telefono = Column(String(20), primary_key=True)
    ventana_iniciada_en = Column(DateTime, nullable=False)
    cantidad = Column(Integer, default=0, nullable=False)
