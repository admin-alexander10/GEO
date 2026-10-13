from typing import List, Optional

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    code: str
    name: str
    price: float
    currency: str = "PEN"
    interval: str = "monthly"
    tier: str = "free"
    included_users: int = 1
    extra_seat_price: float = 0.0
    features: List[str] = []
    stripe_price_id: Optional[str] = None


class CreateCheckoutRequest(BaseModel):
    # El usuario real se toma del token de sesión; este campo se acepta solo por compatibilidad.
    usuario: Optional[str] = Field(default=None, max_length=100)
    plan_code: str = Field(..., min_length=2, max_length=50)
    # Pago reportado (obligatorio en planes de pago cuando no hay pasarela configurada).
    payment_method: Optional[str] = Field(default=None, max_length=40)
    payment_reference: Optional[str] = Field(default=None, max_length=120)


class ConfirmCheckoutRequest(BaseModel):
    session_id: str = Field(..., min_length=5, max_length=200)


class CheckoutSessionResponse(BaseModel):
    status: str
    provider: str
    plan_code: str
    usuario: str
    checkout_url: Optional[str] = None
    message: str
    requires_manual_confirmation: bool = False


class SubscriptionStatusResponse(BaseModel):
    usuario: str
    plan_code: str
    status: str
    provider: str
    price: float
    currency: str = "PEN"
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    # Solicitud de cambio de plan que aún no está pagada/validada (si existe).
    pending_plan_code: Optional[str] = None
    pending_status: Optional[str] = None


class PaymentReviewItem(BaseModel):
    id: int
    usuario: str
    plan_code: str
    status: str
    provider: str
    price: float
    currency: str = "PEN"
    created_at: Optional[str] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None


class PaymentMethodInfo(BaseModel):
    code: str
    label: str
    destination: str


class PaymentInfoResponse(BaseModel):
    # "manual": el usuario paga por fuera y reporta la operación. "stripe": checkout en la pasarela.
    gateway: str
    account_holder: str
    methods: List[PaymentMethodInfo]


class PaymentReviewRequest(BaseModel):
    review_notes: Optional[str] = Field(default=None, max_length=500)


class InstitutionMemberRequest(BaseModel):
    institution_name: str = Field(..., min_length=2, max_length=120)
    member_name: str = Field(..., min_length=2, max_length=120)
    member_email: str = Field(..., min_length=5, max_length=200)
    role: str = Field(default="operador", min_length=2, max_length=60)
    total_users: int = Field(default=1, ge=1)


class InstitutionMemberUpdate(BaseModel):
    role: Optional[str] = Field(default=None, min_length=2, max_length=60)
    is_active: Optional[bool] = None


class InstitutionPlanUpdate(BaseModel):
    plan_code: str = Field(..., min_length=2, max_length=50)

class InstitutionMemberResponse(BaseModel):
    id: int
    institution_name: str
    member_name: str
    member_email: str
    role: str
    is_active: bool
    monthly_price: float
    created_at: Optional[str] = None


class InstitutionInviteResponse(BaseModel):
    id: int
    institution_name: str
    member_name: str
    member_email: str
    role: str
    invitation_url: str
    expires_at: str
    monthly_price: float


class InstitutionInviteAcceptRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=200)
    password: str = Field(..., min_length=12, max_length=128)


class InstitutionPricingResponse(BaseModel):
    institution_name: str
    plan_code: str
    included_users: int
    total_users: int
    extra_users: int
    extra_seat_price: float
    monthly_total: float
    currency: str = "PEN"


class InstitutionAccountResponse(InstitutionPricingResponse):
    is_active: bool
    active_members: int
