from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.db.base import Base


class PlanCatalog(Base):
    """Catálogo de planes disponibles para suscripción comercial."""

    __tablename__ = "plan_catalog"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), nullable=False, default="PEN")
    interval = Column(String(30), nullable=False, default="monthly")
    tier = Column(String(30), nullable=False, default="free")
    included_users = Column(Integer, nullable=False, default=1)
    extra_seat_price = Column(Float, nullable=False, default=0.0)
    features = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    stripe_price_id = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserSubscription(Base):
    """Suscripción activa asociada a cada usuario."""

    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    usuario = Column(String(100), index=True, nullable=False)
    plan_code = Column(String(50), index=True, nullable=False)
    status = Column(String(40), default="active", nullable=False)
    provider = Column(String(40), default="stripe", nullable=False)
    price = Column(Float, default=0.0, nullable=False)
    currency = Column(String(10), default="PEN", nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    checkout_session_id = Column(String(200), nullable=True)
    customer_id = Column(String(200), nullable=True)
    # Pago reportado por el usuario (Yape, Plin o transferencia) para validación manual.
    payment_method = Column(String(40), nullable=True)
    payment_reference = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstitutionAccount(Base):
    """Cuenta institucional con múltiples usuarios y acceso compartido."""

    __tablename__ = "institution_accounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institution_name = Column(String(120), unique=True, index=True, nullable=False)
    plan_code = Column(String(50), default="enterprise", nullable=False)
    included_users = Column(Integer, default=5, nullable=False)
    extra_seat_price = Column(Float, default=35.0, nullable=False)
    monthly_total = Column(Float, default=0.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Cobertura geográfica: un círculo (centro + radio) que el propietario de la
    # plataforma valida contra una evidencia. Mientras coverage_validated_at sea
    # NULL la institución no recibe alertas de forma automática.
    coverage_lat = Column(Float, nullable=True)
    coverage_lng = Column(Float, nullable=True)
    coverage_radius_km = Column(Float, nullable=True)
    coverage_evidence = Column(Text, nullable=True)
    coverage_validated_by = Column(String(120), nullable=True)
    coverage_validated_at = Column(DateTime, nullable=True)


class InstitutionMember(Base):
    """Usuario extra dentro de una institución que puede ver incidentes en tiempo real."""

    __tablename__ = "institution_members"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institution_name = Column(String(120), index=True, nullable=False)
    member_name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=False)
    role = Column(String(60), default="operador", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstitutionInvite(Base):
    __tablename__ = "institution_invites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institution_name = Column(String(120), index=True, nullable=False)
    member_name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=False, index=True)
    role = Column(String(60), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstitutionApplication(Base):
    __tablename__ = "institution_applications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institution_name = Column(String(120), index=True, nullable=False)
    ruc = Column(String(11), unique=True, index=True, nullable=False)
    institution_type = Column(String(60), nullable=False)
    region = Column(String(100), nullable=False)
    official_email = Column(String(200), nullable=False)
    contact_name = Column(String(120), nullable=False)
    contact_phone = Column(String(40), nullable=False)
    evidence_url = Column(String(500), nullable=False)
    applicant_username = Column(String(100), index=True, nullable=False)
    status = Column(String(20), default="pending", index=True, nullable=False)
    verification_source = Column(String(500), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_by = Column(String(120), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)


class PlatformAdminAccount(Base):
    __tablename__ = "platform_admin_accounts"

    id = Column(Integer, primary_key=True)
    password_hash = Column(String(255), nullable=False)
    must_change_password = Column(Boolean, default=True, nullable=False)
    password_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
