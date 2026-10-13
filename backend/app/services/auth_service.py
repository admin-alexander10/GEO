import hashlib
import json
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.services.base_service import BaseService
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegistroRequest, LoginRequest, AuthResponse
from app.core.security import hash_password, verify_password, generar_codigo_enlace, create_access_token, build_permissions_for_role, normalize_role
from app.models.subscription import InstitutionAccount, InstitutionApplication, InstitutionInvite, InstitutionMember
from app.models.user import Usuario
from app.domain.exceptions import DomainException, EntityAlreadyExistsException, ForbiddenException, InvalidCredentialsException

class AuthService(BaseService):
    """Servicio de autenticación, emisión de credenciales y autorización RBAC."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.user_repo = UserRepository(db)

    def registrar_usuario(self, data: RegistroRequest) -> AuthResponse:
        # 1. Validar unicidad
        existente = self.user_repo.get_by_username(data.usuario)
        puede_solicitar_conversion = bool(
            existente
            and data.modo == "institucional"
            and normalize_role(existente.rol) == "ciudadano"
            and getattr(existente, "institucion", "individual") in (None, "individual")
            and getattr(existente, "is_active", 1)
            and verify_password(data.password, existente.password)
        )
        if existente and not puede_solicitar_conversion:
            raise EntityAlreadyExistsException("Usuario", data.usuario)

        if data.modo == "institucional":
            institution_name = (data.nombre_institucion or "").strip()
            if not institution_name:
                raise DomainException("Indica el nombre de la institución pública.", code="VALIDATION_ERROR")
            required_application_fields = {
                "RUC": data.ruc_institucion,
                "tipo de institución": data.tipo_institucion,
                "región": data.region_institucion,
                "correo institucional": data.correo_institucional,
                "persona de contacto": data.contacto_institucional,
                "teléfono": data.telefono_institucional,
                "enlace de evidencia oficial": data.evidencia_institucional_url,
            }
            missing_fields = [label for label, value in required_application_fields.items() if not value or not value.strip()]
            if missing_fields:
                raise DomainException(
                    "Completa los datos de verificación institucional: " + ", ".join(missing_fields),
                    code="VALIDATION_ERROR",
                )
            if not data.evidencia_institucional_url.startswith("https://"):
                raise DomainException("El enlace de evidencia debe usar HTTPS.", code="VALIDATION_ERROR")
            existing_institution = self.db.query(InstitutionAccount).filter(
                InstitutionAccount.institution_name == institution_name
            ).first() if institution_name else None
            if existing_institution:
                raise EntityAlreadyExistsException("Institución", institution_name)
            existing_ruc = self.db.query(InstitutionApplication).filter(
                InstitutionApplication.ruc == data.ruc_institucion
            ).first()
            if existing_ruc:
                raise EntityAlreadyExistsException("RUC", data.ruc_institucion)
            if existente:
                solicitud_pendiente = self.db.query(InstitutionApplication).filter(
                    InstitutionApplication.applicant_username == existente.usuario,
                    InstitutionApplication.status == "pending",
                ).first()
                if solicitud_pendiente:
                    raise EntityAlreadyExistsException("Solicitud institucional pendiente de", existente.usuario)
            from app.services.subscription_service import SubscriptionService

            plan = SubscriptionService(self.db).get_plan_by_code("enterprise")
            if not plan:
                raise DomainException("El plan institucional no está disponible.", code="PLAN_UNAVAILABLE")
            role = "director"
            permissions = build_permissions_for_role(role)
            es_conversion = existente is not None
            if es_conversion:
                # Un ciudadano que solicita pasar a institucional conserva su cuenta
                # ciudadana activa (y su acceso al SOS) hasta que la solicitud se apruebe.
                # El rol de director se asigna recién en la aprobación.
                institution_user = existente
                code = existente.codigo_enlace
            else:
                code = generar_codigo_enlace()
                institution_user = Usuario(
                    usuario=data.usuario,
                    password=hash_password(data.password),
                    codigo_enlace=code,
                    rol=role,
                    institucion=institution_name,
                    permisos=json.dumps(permissions),
                    is_active=0,
                )
            institution = InstitutionAccount(
                institution_name=institution_name,
                plan_code=plan.code,
                included_users=int(plan.included_users or 1),
                extra_seat_price=float(plan.extra_seat_price or 0.0),
                monthly_total=float(plan.price or 0.0),
                is_active=False,
            )
            application = InstitutionApplication(
                institution_name=institution_name,
                ruc=data.ruc_institucion,
                institution_type=data.tipo_institucion,
                region=data.region_institucion,
                official_email=data.correo_institucional,
                contact_name=data.contacto_institucional,
                contact_phone=data.telefono_institucional,
                evidence_url=data.evidencia_institucional_url,
                applicant_username=institution_user.usuario,
            )
            self.db.add_all([institution_user, institution, application])
            try:
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                raise EntityAlreadyExistsException("Solicitud institucional", institution_name) from exc
            self.db.refresh(institution_user)
            mensaje = (
                "Solicitud institucional recibida. Los propietarios verificarán los datos y la evidencia antes de habilitar el acceso."
            )
            if es_conversion:
                mensaje += " Mientras tanto, tu cuenta ciudadana sigue activa en el acceso Familiar."
            # En una conversión la respuesta refleja el estado real de la cuenta (sigue siendo ciudadana).
            rol_actual = normalize_role(institution_user.rol)
            return AuthResponse(
                mensaje=mensaje,
                usuario=institution_user.usuario,
                rol=rol_actual,
                institucion=getattr(institution_user, "institucion", None) or "individual",
                permisos=build_permissions_for_role(rol_actual),
                token=None,
                codigo_enlace=code,
            )

        # El registro público solo crea cuentas ciudadanas; los roles institucionales
        # deben asignarse mediante un proceso de provisión autenticado.
        rol = "ciudadano"
        institucion = "individual"
        permisos = build_permissions_for_role(rol)

        # 2. Hashear contraseña y generar código de enlace familiar
        pwd_hash = hash_password(data.password)
        codigo = generar_codigo_enlace()

        # 3. Persistir en repositorio
        nuevo_usuario = self.user_repo.create_user(
            usuario=data.usuario,
            password_hash=pwd_hash,
            rol=rol,
            institucion=institucion,
            permisos=permisos,
            codigo_enlace=codigo
        )

        # 4. Generar Token JWT
        token = create_access_token({
            "sub": nuevo_usuario.usuario,
            "rol": nuevo_usuario.rol,
            "institucion": getattr(nuevo_usuario, "institucion", institucion),
            "permisos": permisos,
            "codigo_enlace": nuevo_usuario.codigo_enlace
        })

        return AuthResponse(
            mensaje="Usuario registrado exitosamente en GEORESCUE IA",
            usuario=nuevo_usuario.usuario,
            rol=nuevo_usuario.rol,
            institucion=getattr(nuevo_usuario, "institucion", institucion),
            permisos=permisos,
            token=token,
            codigo_enlace=nuevo_usuario.codigo_enlace
        )

    def autenticar_usuario(self, data: LoginRequest) -> AuthResponse:
        # 1. Buscar usuario
        usuario = self.user_repo.get_by_username(data.usuario)
        if not usuario:
            raise InvalidCredentialsException("Usuario o contraseña incorrectos.")

        # 2. Verificar hash
        if not verify_password(data.password, usuario.password):
            raise InvalidCredentialsException("Usuario o contraseña incorrectos.")

        # 2.1 Cuenta desactivada: solo con la contraseña correcta se explica el motivo,
        # para que un director pendiente no vea un falso "contraseña incorrecta".
        if not getattr(usuario, "is_active", 1):
            raise ForbiddenException(self._motivo_cuenta_inactiva(usuario))

        rol = normalize_role(getattr(usuario, "rol", "ciudadano"))
        institucion = getattr(usuario, "institucion", data.institucion or "individual")
        es_cuenta_institucional = rol != "ciudadano" and institucion != "individual"
        if (data.modo == "institucional") != es_cuenta_institucional:
            # La contraseña ya se verificó, así que se puede indicar la pestaña correcta.
            raise InvalidCredentialsException(
                "Esta cuenta es institucional: ingresa por la pestaña 'Institucional'."
                if es_cuenta_institucional
                else "Esta cuenta es ciudadana: ingresa por la pestaña 'Familiar'."
            )
        permisos = build_permissions_for_role(rol)

        # 3. Generar Token JWT con claims
        token = create_access_token({
            "sub": usuario.usuario,
            "rol": rol,
            "institucion": institucion,
            "permisos": permisos,
            "codigo_enlace": usuario.codigo_enlace
        })

        return AuthResponse(
            mensaje="Acceso concedido al sistema GEORESCUE IA",
            usuario=usuario.usuario,
            rol=rol,
            institucion=institucion,
            permisos=permisos,
            token=token,
            codigo_enlace=usuario.codigo_enlace
        )

    def _motivo_cuenta_inactiva(self, usuario: Usuario) -> str:
        solicitud = self.db.query(InstitutionApplication).filter(
            InstitutionApplication.applicant_username == usuario.usuario
        ).order_by(InstitutionApplication.id.desc()).first()
        if solicitud and solicitud.status == "pending":
            return (
                "Tu solicitud institucional está pendiente de revisión. "
                "Podrás ingresar cuando los propietarios de la plataforma la aprueben."
            )
        if solicitud and solicitud.status == "rejected":
            return "Tu solicitud institucional fue rechazada. Contacta a los propietarios de la plataforma."
        return "Tu cuenta está desactivada. Contacta al coordinador de tu institución."

    def aceptar_invitacion(self, token: str, password: str) -> AuthResponse:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        invite = self.db.query(InstitutionInvite).filter(
            InstitutionInvite.token_hash == token_hash,
            InstitutionInvite.accepted_at.is_(None),
            InstitutionInvite.expires_at > datetime.utcnow(),
        ).first()
        if not invite:
            raise InvalidCredentialsException("La invitación es inválida, ya fue usada o expiró.")
        if self.user_repo.get_by_username(invite.email):
            raise EntityAlreadyExistsException("Usuario", invite.email)

        permissions = build_permissions_for_role(invite.role)
        code = generar_codigo_enlace()
        account = Usuario(
            usuario=invite.email,
            password=hash_password(password),
            rol=invite.role,
            institucion=invite.institution_name,
            permisos=json.dumps(permissions),
            codigo_enlace=code,
            is_active=1,
        )
        self.db.add_all([
            account,
            InstitutionMember(
                institution_name=invite.institution_name,
                member_name=invite.member_name,
                email=invite.email,
                role=invite.role,
                is_active=True,
            ),
        ])
        invite.accepted_at = datetime.utcnow()
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(account)

        token_jwt = create_access_token({
            "sub": account.usuario,
            "rol": invite.role,
            "institucion": invite.institution_name,
            "permisos": permissions,
            "codigo_enlace": account.codigo_enlace,
        })
        return AuthResponse(
            mensaje="Invitación aceptada. Cuenta institucional creada.",
            usuario=account.usuario,
            rol=invite.role,
            institucion=invite.institution_name,
            permisos=permissions,
            token=token_jwt,
            codigo_enlace=account.codigo_enlace,
        )
