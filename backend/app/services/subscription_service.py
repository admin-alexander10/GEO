import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.subscription import InstitutionAccount, InstitutionInvite, InstitutionMember, PlanCatalog, UserSubscription
from app.models.user import Usuario
from app.schemas.subscription import (
    CheckoutSessionResponse,
    CreateCheckoutRequest,
    InstitutionMemberResponse,
    PaymentInfoResponse,
    PaymentMethodInfo,
    InstitutionPricingResponse,
    PlanItem,
    SubscriptionStatusResponse,
)

try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None


class SubscriptionService:
    """Módulo de suscripciones y planes comerciales realista para producción."""

    def __init__(self, db: Session):
        self.db = db

    def ensure_default_plans(self) -> List[PlanCatalog]:
        defaults = [
            {
                "code": "free",
                "name": "Free",
                "price": 0.0,
                "currency": "PEN",
                "interval": "monthly",
                "tier": "free",
                "included_users": 1,
                "extra_seat_price": 0.0,
                "features": ["1 usuario", "SOS básico", "Red familiar"],
                "stripe_price_id": None,
            },
            {
                "code": "pro",
                "name": "Pro",
                "price": 39.0,
                "currency": "PEN",
                "interval": "monthly",
                "tier": "pro",
                "included_users": 5,
                "extra_seat_price": 25.0,
                "features": ["Alertas avanzadas", "Mapa geolocalizado", "Captura antirrobo"],
                "stripe_price_id": settings.STRIPE_PRICE_ID_PRO,
            },
            {
                "code": "enterprise",
                "name": "Enterprise",
                "price": 299.0,
                "currency": "PEN",
                "interval": "custom",
                "tier": "enterprise",
                "included_users": 10,
                "extra_seat_price": 35.0,
                "features": ["Multi-sede", "Integración B2G", "Múltiples usuarios institucionales"],
                "stripe_price_id": settings.STRIPE_PRICE_ID_ENTERPRISE,
            },
        ]

        created: List[PlanCatalog] = []
        for plan in defaults:
            existing = self.db.query(PlanCatalog).filter(PlanCatalog.code == plan["code"]).first()
            if existing:
                existing.included_users = int(plan["included_users"])
                existing.extra_seat_price = float(plan["extra_seat_price"])
                existing.price = float(plan["price"])
                self.db.add(existing)
                continue
            record = PlanCatalog(
                code=plan["code"],
                name=plan["name"],
                price=float(plan["price"]),
                currency=plan["currency"],
                interval=plan["interval"],
                tier=plan["tier"],
                included_users=int(plan["included_users"]),
                extra_seat_price=float(plan["extra_seat_price"]),
                features=json.dumps(plan["features"]),
                stripe_price_id=plan["stripe_price_id"],
                is_active=True,
            )
            self.db.add(record)
            created.append(record)

        if created:
            self.db.commit()
            for item in created:
                self.db.refresh(item)
        else:
            self.db.commit()

        return self.db.query(PlanCatalog).filter(PlanCatalog.is_active.is_(True)).order_by(PlanCatalog.id).all()

    def list_plans(self) -> List[PlanItem]:
        self.ensure_default_plans()
        items = self.db.query(PlanCatalog).filter(PlanCatalog.is_active.is_(True)).order_by(PlanCatalog.id).all()
        response: List[PlanItem] = []
        for plan in items:
            features = json.loads(plan.features) if plan.features else []
            response.append(
                PlanItem(
                    code=plan.code,
                    name=plan.name,
                    price=float(plan.price),
                    currency=plan.currency,
                    interval=plan.interval,
                    tier=plan.tier,
                    included_users=int(plan.included_users or 1),
                    extra_seat_price=float(plan.extra_seat_price or 0.0),
                    features=features,
                    stripe_price_id=plan.stripe_price_id,
                )
            )
        return response

    def get_plan_by_code(self, plan_code: str) -> PlanCatalog:
        self.ensure_default_plans()
        return self.db.query(PlanCatalog).filter(PlanCatalog.code == plan_code, PlanCatalog.is_active.is_(True)).first()

    def calculate_institution_total(self, plan_code: str, total_users: int) -> float:
        plan = self.get_plan_by_code(plan_code)
        if not plan:
            raise ValueError(f"El plan '{plan_code}' no existe o no está habilitado.")

        included_users = int(getattr(plan, "included_users", 1) or 1)
        extra_seat_price = float(getattr(plan, "extra_seat_price", 0.0) or 0.0)
        extra_users = max(0, int(total_users) - included_users)
        return float(plan.price) + (extra_users * extra_seat_price)

    def add_institution_member(
        self,
        institution_name: str,
        member_name: str,
        member_email: str,
        role: str = "operador",
        total_users: int = 1,
    ):
        role = role.strip().lower()
        if role not in {"operador", "analista", "coordinador"}:
            raise ValueError("El rol debe ser operador, analista o coordinador.")
        existing_member = self.db.query(InstitutionMember).filter(
            InstitutionMember.institution_name == institution_name,
            InstitutionMember.email == member_email,
        ).first()
        if existing_member is not None and getattr(existing_member, "email", None) == member_email:
            raise ValueError("El correo ya pertenece a esta cuenta institucional.")
        plan = self.get_plan_by_code("enterprise")
        if not plan:
            plan = self.get_plan_by_code("pro") or self.get_plan_by_code("free")

        monthly_price = self.calculate_institution_total(plan.code if plan else "enterprise", total_users)

        institution = self.db.query(InstitutionAccount).filter(InstitutionAccount.institution_name == institution_name).first()
        if not institution:
            institution = InstitutionAccount(
                institution_name=institution_name,
                plan_code=plan.code if plan else "enterprise",
                included_users=int(getattr(plan, "included_users", 1) or 1),
                extra_seat_price=float(getattr(plan, "extra_seat_price", 0.0) or 0.0),
                monthly_total=monthly_price,
                is_active=True,
            )
            self.db.add(institution)
            self.db.commit()
            self.db.refresh(institution)
        else:
            institution.plan_code = plan.code if plan else "enterprise"
            institution.included_users = int(getattr(plan, "included_users", 1) or 1)
            institution.extra_seat_price = float(getattr(plan, "extra_seat_price", 0.0) or 0.0)
            institution.monthly_total = monthly_price
            self.db.add(institution)

        member = InstitutionMember(
            institution_name=institution_name,
            member_name=member_name,
            email=member_email,
            role=role,
            is_active=True,
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)

        return {
            "id": member.id,
            "institution_name": institution_name,
            "member_name": member_name,
            "member_email": member_email,
            "role": role,
            "is_active": True,
            "monthly_price": float(monthly_price),
            "created_at": member.created_at.isoformat() if member.created_at else None,
        }

    def create_institution_invite(
        self, institution_name: str, member_name: str, member_email: str, role: str
    ):
        role = role.strip().lower()
        if role not in {"operador", "analista", "coordinador"}:
            raise ValueError("El rol debe ser operador, analista o coordinador.")
        account = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution_name,
            InstitutionAccount.is_active.is_(True),
        ).first()
        if not account:
            raise ValueError("La cuenta institucional no existe o está desactivada.")
        if self.db.query(Usuario).filter(Usuario.usuario == member_email).first():
            raise ValueError("Ya existe una cuenta con ese correo.")
        pending = self.db.query(InstitutionInvite).filter(
            InstitutionInvite.institution_name == institution_name,
            InstitutionInvite.email == member_email,
            InstitutionInvite.accepted_at.is_(None),
            InstitutionInvite.expires_at > datetime.utcnow(),
        ).first()
        if pending:
            raise ValueError("Ya existe una invitación vigente para ese correo.")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=48)
        invite = InstitutionInvite(
            institution_name=institution_name,
            member_name=member_name,
            email=member_email,
            role=role,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=expires_at,
        )
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        active_members = self.db.query(InstitutionMember).filter(
            InstitutionMember.institution_name == institution_name,
            InstitutionMember.is_active.is_(True),
        ).count()
        pending_invites = self.db.query(InstitutionInvite).filter(
            InstitutionInvite.institution_name == institution_name,
            InstitutionInvite.accepted_at.is_(None),
            InstitutionInvite.expires_at > datetime.utcnow(),
        ).count()
        pricing = self.get_institution_pricing(institution_name)
        monthly_total = self.calculate_institution_total(
            account.plan_code, max(1, active_members + pending_invites + 1)
        )
        account.monthly_total = monthly_total
        self.db.add(account)
        self.db.commit()
        return {
            "id": invite.id,
            "institution_name": institution_name,
            "member_name": member_name,
            "member_email": member_email,
            "role": role,
            "invitation_url": f"{settings.APP_BASE_URL.rstrip('/')}/?invite={token}",
            "expires_at": expires_at.isoformat(),
            "monthly_price": max(pricing.monthly_total, monthly_total),
        }

    def get_institution_pricing(self, institution_name: str) -> InstitutionPricingResponse:
        institution = self.db.query(InstitutionAccount).filter(InstitutionAccount.institution_name == institution_name).first()
        if not institution:
            plan = self.get_plan_by_code("enterprise") or self.get_plan_by_code("pro")
            included_users = int(getattr(plan, "included_users", 1) or 1)
            extra_seat_price = float(getattr(plan, "extra_seat_price", 0.0) or 0.0)
            count = self.db.query(InstitutionMember).filter(InstitutionMember.institution_name == institution_name).count() if hasattr(self.db, 'query') else 0
            total_users = max(1, count + 1)
            total = self.calculate_institution_total(plan.code if plan else "enterprise", total_users)
            return InstitutionPricingResponse(
                institution_name=institution_name,
                plan_code=plan.code if plan else "enterprise",
                included_users=included_users,
                total_users=total_users,
                extra_users=max(0, total_users - included_users),
                extra_seat_price=extra_seat_price,
                monthly_total=total,
                currency="PEN",
            )

        count = self.db.query(InstitutionMember).filter(InstitutionMember.institution_name == institution_name, InstitutionMember.is_active.is_(True)).count()
        pending_invites = self.db.query(InstitutionInvite).filter(
            InstitutionInvite.institution_name == institution_name,
            InstitutionInvite.accepted_at.is_(None),
            InstitutionInvite.expires_at > datetime.utcnow(),
        ).count()
        total_users = max(1, count + pending_invites + 1)
        total = self.calculate_institution_total(institution.plan_code or "enterprise", total_users)
        return InstitutionPricingResponse(
            institution_name=institution.institution_name,
            plan_code=institution.plan_code,
            included_users=institution.included_users,
            total_users=total_users,
            extra_users=max(0, total_users - institution.included_users),
            extra_seat_price=institution.extra_seat_price,
            monthly_total=total,
            currency="PEN",
        )

    def list_institution_members(self, institution_name: str) -> List[InstitutionMemberResponse]:
        members = self.db.query(InstitutionMember).filter(
            InstitutionMember.institution_name == institution_name,
        ).order_by(InstitutionMember.created_at.desc()).all()
        pricing = self.get_institution_pricing(institution_name)
        response = []
        for member in members:
            response.append(
                InstitutionMemberResponse(
                    id=member.id,
                    institution_name=member.institution_name,
                    member_name=member.member_name,
                    member_email=member.email,
                    role=member.role,
                    is_active=member.is_active,
                    monthly_price=float(pricing.monthly_total),
                    created_at=member.created_at.isoformat() if member.created_at else None,
                )
            )
        return response

    def get_institution_account(self, institution_name: str):
        institution = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution_name
        ).first()
        if not institution:
            raise ValueError("La cuenta institucional no existe.")
        pricing = self.get_institution_pricing(institution_name)
        active_members = self.db.query(InstitutionMember).filter(
            InstitutionMember.institution_name == institution_name,
            InstitutionMember.is_active.is_(True),
        ).count()
        return {
            **pricing.dict(),
            "is_active": bool(institution.is_active),
            "active_members": active_members,
        }

    def update_institution_plan(self, institution_name: str, plan_code: str):
        institution = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution_name
        ).first()
        if not institution:
            raise ValueError("La cuenta institucional no existe.")
        plan = self.get_plan_by_code(plan_code)
        if not plan:
            raise ValueError("El plan no existe o no está habilitado.")
        active_members = self.db.query(InstitutionMember).filter(
            InstitutionMember.institution_name == institution_name,
            InstitutionMember.is_active.is_(True),
        ).count()
        pending_invites = self.db.query(InstitutionInvite).filter(
            InstitutionInvite.institution_name == institution_name,
            InstitutionInvite.accepted_at.is_(None),
            InstitutionInvite.expires_at > datetime.utcnow(),
        ).count()
        institution.plan_code = plan.code
        institution.included_users = int(plan.included_users or 1)
        institution.extra_seat_price = float(plan.extra_seat_price or 0.0)
        institution.monthly_total = self.calculate_institution_total(
            plan.code, max(1, active_members + pending_invites + 1)
        )
        self.db.add(institution)
        self.db.commit()
        self.db.refresh(institution)
        return self.get_institution_account(institution_name)

    def update_institution_member(
        self, institution_name: str, member_id: int, role: Optional[str], is_active: Optional[bool]
    ):
        member = self.db.query(InstitutionMember).filter(
            InstitutionMember.id == member_id,
            InstitutionMember.institution_name == institution_name,
        ).first()
        if not member:
            raise ValueError("El miembro no existe en esta cuenta institucional.")
        allowed_roles = {"operador", "analista", "coordinador"}
        if role is not None:
            normalized_role = role.strip().lower()
            if normalized_role not in allowed_roles:
                raise ValueError("El rol debe ser operador, analista o coordinador.")
            member.role = normalized_role
            user_account = self.db.query(Usuario).filter(Usuario.usuario == member.email).first()
            if user_account:
                user_account.rol = normalized_role
                self.db.add(user_account)
        if is_active is not None:
            member.is_active = is_active
            user_account = self.db.query(Usuario).filter(Usuario.usuario == member.email).first()
            if user_account:
                user_account.is_active = int(is_active)
                self.db.add(user_account)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        account = self.db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution_name
        ).first()
        if account:
            pricing = self.get_institution_pricing(institution_name)
            account.monthly_total = pricing.monthly_total
            self.db.add(account)
            self.db.commit()
        pricing = self.get_institution_pricing(institution_name)
        return InstitutionMemberResponse(
            id=member.id,
            institution_name=member.institution_name,
            member_name=member.member_name,
            member_email=member.email,
            role=member.role,
            is_active=member.is_active,
            monthly_price=pricing.monthly_total,
            created_at=member.created_at.isoformat() if member.created_at else None,
        )

    # ------------------------------------------------------------------
    # Pagos de planes individuales (ciudadano)
    # ------------------------------------------------------------------
    ESTADOS_EN_CURSO = ("pending", "manual_review")
    METODOS_DE_PAGO = {"yape": "Yape", "plin": "Plin", "transferencia": "Transferencia bancaria"}

    def _stripe_enabled(self) -> bool:
        return bool(settings.STRIPE_SECRET_KEY) and stripe is not None

    def get_payment_info(self) -> PaymentInfoResponse:
        """Datos que el usuario necesita para pagar por fuera y reportar la operación."""
        destinos = {
            "yape": settings.PAYMENT_YAPE_NUMBER,
            "plin": settings.PAYMENT_PLIN_NUMBER,
            "transferencia": settings.PAYMENT_BANK_ACCOUNT,
        }
        return PaymentInfoResponse(
            gateway="stripe" if self._stripe_enabled() else "manual",
            account_holder=settings.PAYMENT_ACCOUNT_HOLDER,
            methods=[
                PaymentMethodInfo(code=code, label=label, destination=destinos[code])
                for code, label in self.METODOS_DE_PAGO.items()
            ],
        )

    def _validar_pago_reportado(self, request: CreateCheckoutRequest, usuario: str) -> tuple[str, str]:
        metodo = (request.payment_method or "").strip().lower()
        referencia = " ".join((request.payment_reference or "").split())
        if metodo not in self.METODOS_DE_PAGO:
            raise ValueError("Elige el método con el que pagaste: Yape, Plin o transferencia.")
        if len(referencia) < 4:
            raise ValueError("Escribe el número de operación que aparece en tu comprobante de pago.")
        # Un mismo comprobante no puede usarse para dos solicitudes distintas.
        repetido = self.db.query(UserSubscription).filter(
            UserSubscription.payment_method == metodo,
            UserSubscription.payment_reference == referencia,
            UserSubscription.status.in_(("manual_review", "active", "replaced")),
            UserSubscription.usuario != usuario,
        ).first()
        if repetido:
            raise ValueError("Ese número de operación ya fue registrado por otra cuenta.")
        return metodo, referencia

    def _open_request(self, usuario: str) -> Optional[UserSubscription]:
        """Solicitud de plan que aún no está pagada ni validada (como máximo una por usuario)."""
        return self.db.query(UserSubscription).filter(
            UserSubscription.usuario == usuario,
            UserSubscription.status.in_(self.ESTADOS_EN_CURSO),
        ).order_by(UserSubscription.id.desc()).first()

    def _active_subscription(self, usuario: str) -> Optional[UserSubscription]:
        now = datetime.utcnow()
        candidates = self.db.query(UserSubscription).filter(
            UserSubscription.usuario == usuario,
            UserSubscription.status == "active",
        ).order_by(UserSubscription.id.desc()).all()
        for item in candidates:
            if item.expires_at is None or item.expires_at > now:
                return item
        return None

    def _activate(self, subscription: UserSubscription) -> None:
        """Activa una suscripción y reemplaza la que estuviera vigente."""
        now = datetime.utcnow()
        self.db.add(subscription)
        self.db.flush()  # asegura que la fila nueva ya tenga id antes de compararla
        previous = self.db.query(UserSubscription).filter(
            UserSubscription.usuario == subscription.usuario,
            UserSubscription.status == "active",
            UserSubscription.id != subscription.id,
        ).all()
        for item in previous:
            item.status = "replaced"
            self.db.add(item)
        subscription.status = "active"
        subscription.started_at = now
        subscription.expires_at = None if float(subscription.price or 0) == 0 else now + timedelta(days=30)
        self.db.add(subscription)

    def create_checkout(self, request: CreateCheckoutRequest) -> CheckoutSessionResponse:
        usuario = (request.usuario or "").strip()
        if not usuario:
            raise ValueError("Inicia sesión para elegir un plan.")
        account = self.db.query(Usuario).filter(Usuario.usuario == usuario).first()
        if not account or not getattr(account, "is_active", 1):
            raise ValueError("La cuenta no existe o está desactivada.")
        if (getattr(account, "institucion", None) or "individual") != "individual":
            raise ValueError("Las cuentas institucionales gestionan su plan desde el panel de la institución.")

        plan = self.get_plan_by_code(request.plan_code)
        if not plan:
            raise ValueError(f"El plan '{request.plan_code}' no existe o no está habilitado.")
        if plan.tier == "enterprise":
            raise ValueError(
                "El plan Enterprise es para instituciones públicas. Regístrate como 'Institución pública' para solicitarlo."
            )

        price = float(plan.price or 0.0)
        active = self._active_subscription(usuario)
        if active and active.plan_code == plan.code:
            return CheckoutSessionResponse(
                status="active",
                provider=active.provider,
                plan_code=plan.code,
                usuario=usuario,
                checkout_url=None,
                message=f"Ya tienes activo el plan {plan.name}.",
                requires_manual_confirmation=False,
            )

        # Una sola solicitud en curso por usuario: se reutiliza en lugar de duplicar filas.
        subscription = self._open_request(usuario)
        if not subscription:
            subscription = UserSubscription(usuario=usuario, plan_code=plan.code, started_at=datetime.utcnow())
        subscription.plan_code = plan.code
        subscription.price = price
        subscription.currency = plan.currency
        subscription.checkout_session_id = None

        # Plan gratuito: se activa de inmediato, no pasa por la pasarela.
        if price == 0:
            subscription.provider = "system"
            self._activate(subscription)
            self.db.commit()
            return CheckoutSessionResponse(
                status="active",
                provider="system",
                plan_code=plan.code,
                usuario=usuario,
                checkout_url=None,
                message="Plan gratuito activado.",
                requires_manual_confirmation=False,
            )

        if self._stripe_enabled():
            stripe.api_key = settings.STRIPE_SECRET_KEY
            base_url = settings.APP_BASE_URL.rstrip("/")
            params = dict(
                mode=settings.STRIPE_CHECKOUT_MODE,
                line_items=[{"price": plan.stripe_price_id or settings.STRIPE_PRICE_ID_PRO, "quantity": 1}],
                # Stripe sustituye {CHECKOUT_SESSION_ID}; el frontend lo usa para confirmar el pago.
                success_url=f"{base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_url}/?checkout=cancel",
                client_reference_id=usuario,
                metadata={"usuario": usuario, "plan_code": plan.code},
            )
            if "@" in usuario:
                params["customer_email"] = usuario
            try:
                session = stripe.checkout.Session.create(**params)
            except Exception as exc:
                raise ValueError(f"La pasarela de pagos rechazó la solicitud: {exc}") from exc

            subscription.status = "pending"
            subscription.provider = "stripe"
            subscription.checkout_session_id = session.id
            subscription.expires_at = None
            self.db.add(subscription)
            self.db.commit()
            return CheckoutSessionResponse(
                status="pending",
                provider="stripe",
                plan_code=plan.code,
                usuario=usuario,
                checkout_url=session.url,
                message=f"Checkout creado para el plan {plan.name}. Completa el pago para activarlo.",
                requires_manual_confirmation=False,
            )

        # Sin pasarela configurada: el usuario paga por fuera, reporta la operación y el
        # propietario la valida contra su cuenta antes de activar el plan.
        metodo, referencia = self._validar_pago_reportado(request, usuario)
        subscription.status = "manual_review"
        subscription.provider = "manual"
        subscription.payment_method = metodo
        subscription.payment_reference = referencia
        subscription.expires_at = None
        self.db.add(subscription)
        self.db.commit()
        return CheckoutSessionResponse(
            status="manual_review",
            provider="manual",
            plan_code=plan.code,
            usuario=usuario,
            checkout_url=None,
            message=(
                f"Pago del plan {plan.name} registrado ({self.METODOS_DE_PAGO[metodo]}, operación {referencia}). "
                "Se activará cuando los propietarios de la plataforma lo validen."
            ),
            requires_manual_confirmation=True,
        )

    def confirm_checkout(self, usuario: str, session_id: str) -> SubscriptionStatusResponse:
        """Consulta a Stripe si la sesión de checkout quedó pagada y, si es así, activa el plan."""
        subscription = self.db.query(UserSubscription).filter(
            UserSubscription.usuario == usuario,
            UserSubscription.checkout_session_id == session_id,
        ).first()
        if not subscription:
            raise ValueError("No existe un pago en curso con ese identificador para tu cuenta.")
        if subscription.status == "pending":
            if not self._stripe_enabled():
                raise ValueError("La pasarela de pagos no está configurada en el servidor.")
            stripe.api_key = settings.STRIPE_SECRET_KEY
            try:
                session = stripe.checkout.Session.retrieve(session_id)
            except Exception as exc:
                raise ValueError(f"No se pudo consultar el pago en la pasarela: {exc}") from exc
            if getattr(session, "payment_status", None) in ("paid", "no_payment_required"):
                subscription.customer_id = getattr(session, "customer", None)
                self._activate(subscription)
                self.db.commit()
        return self.get_user_subscription(usuario)

    def list_payment_requests(self, status_filter: str = "manual_review") -> List[UserSubscription]:
        query = self.db.query(UserSubscription).filter(UserSubscription.provider != "system")
        if status_filter != "all":
            query = query.filter(UserSubscription.status == status_filter)
        return query.order_by(UserSubscription.id.desc()).limit(200).all()

    def review_payment(self, subscription_id: int, approve: bool) -> UserSubscription:
        subscription = self.db.query(UserSubscription).filter(
            UserSubscription.id == subscription_id,
            UserSubscription.status == "manual_review",
        ).first()
        if not subscription:
            raise ValueError("El pago no existe o ya fue revisado.")
        if approve:
            self._activate(subscription)
        else:
            subscription.status = "rejected"
            self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def get_user_subscription(self, usuario: str) -> SubscriptionStatusResponse:
        active = self._active_subscription(usuario)
        open_request = self._open_request(usuario)
        pending_plan_code = open_request.plan_code if open_request else None
        pending_status = open_request.status if open_request else None
        if not active:
            free_plan = self.get_plan_by_code("free")
            return SubscriptionStatusResponse(
                usuario=usuario,
                plan_code="free",
                status="active",
                provider="system",
                price=float(free_plan.price) if free_plan else 0.0,
                currency="PEN",
                started_at=None,
                expires_at=None,
                pending_plan_code=pending_plan_code,
                pending_status=pending_status,
            )

        return SubscriptionStatusResponse(
            usuario=active.usuario,
            plan_code=active.plan_code,
            status=active.status,
            provider=active.provider,
            price=float(active.price or 0.0),
            currency=active.currency or "PEN",
            started_at=active.started_at.isoformat() if active.started_at else None,
            expires_at=active.expires_at.isoformat() if active.expires_at else None,
            pending_plan_code=pending_plan_code,
            pending_status=pending_status,
        )
