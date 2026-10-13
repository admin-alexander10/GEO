from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.subscription import (
    CheckoutSessionResponse,
    ConfirmCheckoutRequest,
    CreateCheckoutRequest,
    InstitutionMemberRequest,
    InstitutionMemberResponse,
    InstitutionMemberUpdate,
    InstitutionInviteResponse,
    InstitutionAccountResponse,
    InstitutionPlanUpdate,
    InstitutionPricingResponse,
    PaymentInfoResponse,
    PlanItem,
    SubscriptionStatusResponse,
)
from app.models.subscription import InstitutionMember
from app.models.subscription import InstitutionAccount
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Suscripciones & Pagos"])


def _institution_from_user(user: dict, requested_name: str | None = None) -> str:
    institution_name = user.get("institucion")
    if not institution_name or institution_name == "individual":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La cuenta no pertenece a una institución.")
    if requested_name and requested_name != institution_name:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes acceder a otra institución.")
    return institution_name

@router.get("/plans", response_model=list[PlanItem])
def listar_planes(db: Session = Depends(get_db)):
    """Devuelve el catálogo de planes disponibles para la interfaz pública."""
    service = SubscriptionService(db)
    return service.list_plans()


@router.get("/payment-info", response_model=PaymentInfoResponse)
def consultar_datos_de_pago(db: Session = Depends(get_db)):
    """Datos de cobro (Yape, Plin, transferencia) que muestra el formulario de pago."""
    return SubscriptionService(db).get_payment_info()


@router.post("/checkout", response_model=CheckoutSessionResponse)
def crear_checkout(
    payload: CreateCheckoutRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inicia la contratación de un plan para la cuenta autenticada.

    Con STRIPE_SECRET_KEY configurada devuelve la URL de pago de Stripe. Sin ella, el usuario
    reporta el pago que hizo por fuera (método y número de operación) y la solicitud queda en
    'manual_review' hasta que un propietario de la plataforma lo valide.
    """
    service = SubscriptionService(db)
    # El titular siempre es quien inició sesión: nadie puede contratar a nombre de otro usuario.
    payload.usuario = user["sub"]
    try:
        return service.create_checkout(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/checkout/confirm", response_model=SubscriptionStatusResponse)
def confirmar_checkout(
    payload: ConfirmCheckoutRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Se llama al volver de Stripe: verifica el pago en la pasarela y activa el plan."""
    try:
        return SubscriptionService(db).confirm_checkout(user["sub"], payload.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/me", response_model=SubscriptionStatusResponse)
def consultar_mi_plan(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Plan vigente de la cuenta autenticada y, si existe, la solicitud de cambio en curso."""
    return SubscriptionService(db).get_user_subscription(user["sub"])


@router.get("/status/{usuario}", response_model=SubscriptionStatusResponse)
def consultar_estado_plan(usuario: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Consulta el plan activo del usuario (solo el propio)."""
    if usuario != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes consultar tu propio plan.")
    service = SubscriptionService(db)
    return service.get_user_subscription(usuario)


@router.get("/institutions/me", response_model=InstitutionAccountResponse, dependencies=[Depends(require_permission("institution:view"))])
def consultar_cuenta_institucional(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    institution_name = _institution_from_user(user)
    service = SubscriptionService(db)
    try:
        return service.get_institution_account(institution_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/institutions/me/members", response_model=list[InstitutionMemberResponse], dependencies=[Depends(require_permission("institution:view"))])
def listar_miembros_de_mi_institucion(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    institution_name = _institution_from_user(user)
    return SubscriptionService(db).list_institution_members(institution_name)


@router.get("/institutions/{institution_name}/pricing", response_model=InstitutionPricingResponse, dependencies=[Depends(require_permission("institution:view"))])
def consultar_precio_institucional(institution_name: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve el costo mensual real según el número de usuarios autorizados dentro de la institución."""
    _institution_from_user(user, institution_name)
    service = SubscriptionService(db)
    return service.get_institution_pricing(institution_name)


@router.get("/institutions/{institution_name}/members", response_model=list[InstitutionMemberResponse], dependencies=[Depends(require_permission("institution:view"))])
def listar_miembros_institucionales(institution_name: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista los usuarios autorizados dentro de la misma institución."""
    _institution_from_user(user, institution_name)
    service = SubscriptionService(db)
    return service.list_institution_members(institution_name)


@router.post("/institutions/members", response_model=InstitutionInviteResponse, dependencies=[Depends(require_permission("institution:manage"))])
def agregar_miembro_institucional(payload: InstitutionMemberRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Invita un miembro a crear su propia cuenta institucional con el rol asignado."""
    institution_name = _institution_from_user(user, payload.institution_name)
    service = SubscriptionService(db)
    try:
        item = service.create_institution_invite(
            institution_name=institution_name,
            member_name=payload.member_name,
            member_email=payload.member_email,
            role=payload.role,
        )
        return InstitutionInviteResponse(**item)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/institutions/me/members/{member_id}", response_model=InstitutionMemberResponse, dependencies=[Depends(require_permission("institution:manage"))])
def actualizar_miembro_institucional(
    member_id: int,
    payload: InstitutionMemberUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    institution_name = _institution_from_user(user)
    service = SubscriptionService(db)
    try:
        return service.update_institution_member(
            institution_name, member_id, payload.role, payload.is_active
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/institutions/me/plan", response_model=InstitutionAccountResponse, dependencies=[Depends(require_permission("billing:manage"))])
def actualizar_plan_institucional(
    payload: InstitutionPlanUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    institution_name = _institution_from_user(user)
    service = SubscriptionService(db)
    try:
        return service.update_institution_plan(institution_name, payload.plan_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
