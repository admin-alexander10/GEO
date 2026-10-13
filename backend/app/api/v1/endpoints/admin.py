import hmac
import json
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import build_permissions_for_role, create_access_token, decode_access_token
from app.db.session import get_db
from app.models.subscription import InstitutionAccount, InstitutionApplication, PlatformAdminAccount
from app.models.user import Usuario
from app.schemas.admin import (
    InstitutionApprovalRequest,
    InstitutionApplicationItem,
    InstitutionCoverageItem,
    InstitutionCoverageRequest,
    InstitutionRejectionRequest,
    InstitutionReviewResponse,
    OwnerLoginRequest,
    OwnerLoginResponse,
    OwnerPasswordChangeRequest,
)
from app.core.security import hash_password, verify_password
from app.schemas.alert import AlertaSinAsignar, AsignacionManualRequest, AsignacionManualResponse
from app.schemas.subscription import PaymentReviewItem
from app.services.alert_service import AlertService
from app.services.realtime import notificar_bandejas
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/admin", tags=["Administración de plataforma"])


def require_platform_owner(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación de propietario requerida.")
    payload = decode_access_token(authorization.split("Bearer ", 1)[1].strip())
    if not payload or payload.get("platform_owner") is not True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso reservado a propietarios de la plataforma.")
    return payload


def require_rotated_platform_owner(owner: dict = Depends(require_platform_owner)) -> dict:
    if owner.get("must_change_password") is not False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cambia la contraseña inicial antes de administrar solicitudes.")
    return owner


@router.post("/login", response_model=OwnerLoginResponse)
def login_propietario(payload: OwnerLoginRequest, request: Request, db: Session = Depends(get_db)):
    account = db.query(PlatformAdminAccount).filter(PlatformAdminAccount.id == 1).first()
    if not account:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "testclient"} or not hmac.compare_digest(payload.access_key, "admin"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La primera configuración solo permite la clave temporal admin desde el mismo equipo.")
        account = PlatformAdminAccount(
            id=1,
            password_hash=hash_password("admin"),
            must_change_password=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    elif not verify_password(payload.access_key, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clave de administración incorrecta.")
    lifetime = timedelta(hours=2)
    token = create_access_token(
        {
            "sub": "platform-owner",
            "rol": "director",
            "platform_owner": True,
            "must_change_password": bool(account.must_change_password),
        },
        expires_delta=lifetime,
    )
    return OwnerLoginResponse(
        access_token=token,
        expires_in=int(lifetime.total_seconds()),
        must_change_password=bool(account.must_change_password),
    )


@router.post("/change-password", response_model=OwnerLoginResponse)
def cambiar_contrasena_propietario(
    payload: OwnerPasswordChangeRequest,
    owner: dict = Depends(require_platform_owner),
    db: Session = Depends(get_db),
):
    account = db.query(PlatformAdminAccount).filter(PlatformAdminAccount.id == 1).first()
    if not account or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La contraseña actual no es correcta.")
    if payload.new_password == "admin" or payload.new_password == payload.current_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Elige una contraseña nueva y distinta a la temporal.")

    from datetime import datetime

    account.password_hash = hash_password(payload.new_password)
    account.must_change_password = False
    account.password_updated_at = datetime.utcnow()
    db.add(account)
    db.commit()
    lifetime = timedelta(hours=2)
    token = create_access_token(
        {"sub": owner.get("sub", "platform-owner"), "rol": "director", "platform_owner": True, "must_change_password": False},
        expires_delta=lifetime,
    )
    return OwnerLoginResponse(access_token=token, expires_in=int(lifetime.total_seconds()), must_change_password=False)


@router.get("/institution-applications", response_model=list[InstitutionApplicationItem])
def listar_solicitudes_institucionales(
    status_filter: str = "pending",
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    if status_filter not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filtro de estado inválido.")
    query = db.query(InstitutionApplication)
    if status_filter != "all":
        query = query.filter(InstitutionApplication.status == status_filter)
    return query.order_by(InstitutionApplication.submitted_at.desc()).all()


@router.post("/institution-applications/{application_id}/approve", response_model=InstitutionReviewResponse)
def aprobar_solicitud(
    application_id: int,
    payload: InstitutionApprovalRequest,
    owner: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    source_url = urlparse(payload.verification_source)
    hostname = (source_url.hostname or "").lower()
    if source_url.scheme != "https" or not (hostname == "gob.pe" or hostname.endswith(".gob.pe")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="La fuente consultada debe pertenecer a un dominio oficial .gob.pe y usar HTTPS.")
    application = db.query(InstitutionApplication).filter(
        InstitutionApplication.id == application_id,
        InstitutionApplication.status == "pending",
    ).with_for_update().first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La solicitud no existe o ya fue revisada.")
    account = db.query(InstitutionAccount).filter(
        InstitutionAccount.institution_name == application.institution_name,
        InstitutionAccount.is_active.is_(False),
    ).first()
    applicant = db.query(Usuario).filter(
        Usuario.usuario == application.applicant_username,
    ).first()
    # El solicitante es una cuenta nueva (director desactivado de esta institución) o un
    # ciudadano que pidió la conversión y sigue como 'individual'. Cualquier otra cosa es un conflicto.
    applicant_institution = getattr(applicant, "institucion", None) or "individual"
    if not account or not applicant or applicant_institution not in ("individual", application.institution_name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No se encontró la cuenta pendiente asociada a esta solicitud.")

    from datetime import datetime

    reviewed_at = datetime.utcnow()
    application.status = "approved"
    application.verification_source = payload.verification_source
    application.review_notes = payload.review_notes
    application.reviewed_by = owner.get("sub", "platform-owner")
    application.reviewed_at = reviewed_at
    account.is_active = True
    applicant.rol = "director"
    applicant.institucion = application.institution_name
    applicant.permisos = json.dumps(build_permissions_for_role("director"))
    applicant.is_active = 1
    db.add_all([application, account, applicant])
    db.commit()
    return InstitutionReviewResponse(
        id=application.id,
        institution_name=application.institution_name,
        status=application.status,
        reviewed_by=application.reviewed_by,
        reviewed_at=reviewed_at,
        message="Institución aprobada. El director ya puede iniciar sesión en modo institucional.",
    )


@router.post("/institution-applications/{application_id}/reject", response_model=InstitutionReviewResponse)
def rechazar_solicitud(
    application_id: int,
    payload: InstitutionRejectionRequest,
    owner: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    application = db.query(InstitutionApplication).filter(
        InstitutionApplication.id == application_id,
        InstitutionApplication.status == "pending",
    ).with_for_update().first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La solicitud no existe o ya fue revisada.")
    from datetime import datetime

    reviewed_at = datetime.utcnow()
    application.status = "rejected"
    application.review_notes = payload.review_notes
    application.reviewed_by = owner.get("sub", "platform-owner")
    application.reviewed_at = reviewed_at
    db.add(application)
    db.commit()
    return InstitutionReviewResponse(
        id=application.id,
        institution_name=application.institution_name,
        status=application.status,
        reviewed_by=application.reviewed_by,
        reviewed_at=reviewed_at,
        message="Solicitud rechazada. La cuenta y el usuario permanecen desactivados.",
    )


# ---------------------------------------------------------------------------
# Validación manual de pagos (cuando no hay pasarela Stripe configurada)
# ---------------------------------------------------------------------------
def _payment_item(subscription) -> PaymentReviewItem:
    return PaymentReviewItem(
        id=subscription.id,
        usuario=subscription.usuario,
        plan_code=subscription.plan_code,
        status=subscription.status,
        provider=subscription.provider,
        price=float(subscription.price or 0.0),
        currency=subscription.currency or "PEN",
        created_at=subscription.created_at.isoformat() if subscription.created_at else None,
        payment_method=getattr(subscription, "payment_method", None),
        payment_reference=getattr(subscription, "payment_reference", None),
    )


@router.get("/payments", response_model=list[PaymentReviewItem])
def listar_pagos(
    status_filter: str = "manual_review",
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    if status_filter not in {"manual_review", "pending", "active", "rejected", "replaced", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filtro de estado inválido.")
    return [_payment_item(item) for item in SubscriptionService(db).list_payment_requests(status_filter)]


@router.post("/payments/{subscription_id}/approve", response_model=PaymentReviewItem)
def aprobar_pago(
    subscription_id: int,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    try:
        return _payment_item(SubscriptionService(db).review_payment(subscription_id, approve=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/payments/{subscription_id}/reject", response_model=PaymentReviewItem)
def rechazar_pago(
    subscription_id: int,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    try:
        return _payment_item(SubscriptionService(db).review_payment(subscription_id, approve=False))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Cobertura geográfica de instituciones y asignación de alertas
# ---------------------------------------------------------------------------
def _institucion_aprobada(db: Session, institution_id: int) -> InstitutionAccount:
    account = db.query(InstitutionAccount).filter(
        InstitutionAccount.id == institution_id,
        InstitutionAccount.is_active.is_(True),
    ).with_for_update().first()
    approved = account and db.query(InstitutionApplication).filter(
        InstitutionApplication.institution_name == account.institution_name,
        InstitutionApplication.status == "approved",
    ).first()
    if not account or not approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La institución no existe o no está aprobada y activa.")
    return account


@router.get("/institutions", response_model=list[InstitutionCoverageItem])
def listar_instituciones_activas(
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Instituciones aprobadas y activas, con la cobertura que tengan validada."""
    aprobadas = select(InstitutionApplication.institution_name).where(
        InstitutionApplication.status == "approved",
    )
    return db.query(InstitutionAccount).filter(
        InstitutionAccount.is_active.is_(True),
        InstitutionAccount.institution_name.in_(aprobadas),
    ).order_by(InstitutionAccount.institution_name).all()


@router.put("/institutions/{institution_id}/coverage", response_model=InstitutionCoverageItem)
def validar_cobertura(
    institution_id: int,
    payload: InstitutionCoverageRequest,
    owner: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Registra la zona que la institución atiende. Desde ese momento recibe en su
    bandeja las alertas nuevas cuya ubicación caiga dentro del círculo."""
    from datetime import datetime

    account = _institucion_aprobada(db, institution_id)
    account.coverage_lat = payload.latitud
    account.coverage_lng = payload.longitud
    account.coverage_radius_km = payload.radio_km
    account.coverage_evidence = payload.evidencia.strip()
    account.coverage_validated_by = owner.get("sub", "platform-owner")
    account.coverage_validated_at = datetime.utcnow()
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/institutions/{institution_id}/coverage", response_model=InstitutionCoverageItem)
def retirar_cobertura(
    institution_id: int,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Deja de asignar alertas nuevas a la institución. Las ya asignadas se conservan."""
    account = db.query(InstitutionAccount).filter(
        InstitutionAccount.id == institution_id,
    ).with_for_update().first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La institución no existe.")
    account.coverage_validated_at = None
    account.coverage_validated_by = None
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/alerts/unassigned", response_model=list[AlertaSinAsignar])
def listar_alertas_sin_asignar(
    limit: int = 50,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Alertas abiertas que ninguna institución tiene en su bandeja."""
    return AlertService(db).listar_sin_asignar(limit=max(1, min(limit, 200)))


@router.post("/alerts/{alert_id}/assign", response_model=AsignacionManualResponse)
async def asignar_alerta(
    alert_id: int,
    payload: AsignacionManualRequest,
    owner: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Asignación manual: para alertas sin ubicación o fuera de toda cobertura."""
    respuesta = AlertService(db).asignar_manualmente(
        alerta_id=alert_id,
        institution_name=payload.institution_name.strip(),
        actor=owner.get("sub", "platform-owner"),
        reason=payload.reason.strip(),
    )
    await notificar_bandejas([payload.institution_name.strip()], alert_id)
    return respuesta
