from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from datetime import datetime
from app.db.base import Base


class RedFamiliar(Base):
    __tablename__ = "red_familiar"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    usuario_responsable = Column(String(100), index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    parentesco = Column(String(80), nullable=False)
    dispositivo_id = Column(String(100), nullable=True)
    familiar_usuario = Column(String(100), nullable=True, index=True)
    consentimiento_en = Column(DateTime, nullable=True)
    revocado_en = Column(DateTime, nullable=True)
    revocado_por = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class FamilyInvitation(Base):
    __tablename__ = "family_invitations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    invitante_usuario = Column(String(100), index=True, nullable=False)
    invitado_usuario = Column(String(100), index=True, nullable=False)
    parentesco = Column(String(80), nullable=False)
    estado = Column(String(20), default="PENDIENTE", nullable=False, index=True)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    respondido_en = Column(DateTime, nullable=True)
