from typing import Optional, List, Dict, Any
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db
from app.services.auth_service import AuthService
from app.services.alert_service import AlertService
from app.services.family_service import FamilyService
from app.services.rescue_service import RescueService
from app.services.coaccion_service import CoaccionService
from app.services.cap_service import CAPService
from app.services.security_service import SecurityService
from app.core.security import decode_access_token, build_permissions_for_role, normalize_role
from app.domain.exceptions import UnauthorizedException, ForbiddenException
from app.models.subscription import InstitutionAccount, InstitutionApplication
from app.models.user import Usuario

# Inyección de dependencias de Base de Datos
def get_db_session() -> Session:
    return Depends(get_db)

# Inyección de dependencias de la Capa de Servicios
def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)

def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(db)

def get_family_service(db: Session = Depends(get_db)) -> FamilyService:
    return FamilyService(db)

def get_rescue_service() -> RescueService:
    return RescueService()

def get_coaccion_service(db: Session = Depends(get_db)) -> CoaccionService:
    return CoaccionService(db)

def get_cap_service(db: Session = Depends(get_db)) -> CAPService:
    return CAPService(db)

def get_security_service(db: Session = Depends(get_db)) -> SecurityService:
    return SecurityService(db)

# Seguridad y Autenticación JWT / RBAC
def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extrae las credenciales del token Bearer JWT si existe en la cabecera."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split("Bearer ", 1)[1].strip()
    return decode_access_token(token)

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Exige un token Bearer JWT válido para acceder al recurso."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabecera Authorization Bearer requerida."
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido o expirado."
        )
    username = payload.get("sub")
    account = db.query(Usuario).filter(Usuario.usuario == username).first() if username else None
    if not account or not getattr(account, "is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La cuenta ya no está activa o no existe."
        )
    role = normalize_role(account.rol)
    institution = getattr(account, "institucion", "individual")
    if role != "ciudadano" and institution != "individual":
        active_institution = db.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == institution,
            InstitutionAccount.is_active.is_(True),
        ).first()
        approved_application = db.query(InstitutionApplication).filter(
            InstitutionApplication.institution_name == institution,
            InstitutionApplication.status == "approved",
        ).first()
        if not active_institution or not approved_application:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La institución no está aprobada y activa en la plataforma.",
            )
    payload["rol"] = role
    payload["institucion"] = institution
    payload["permisos"] = build_permissions_for_role(role)
    return payload


def require_role(allowed_roles: List[str]):
    """Dependencia RBAC para restringir endpoints por rol de usuario."""
    def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = normalize_role(user.get("rol", "ciudadano"))
        if user_role not in [normalize_role(role) for role in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere uno de los siguientes roles: {allowed_roles}"
            )
        return user
    return role_checker


def require_permission(required_permission: str):
    """Dependencia RBAC para validar permisos explícitos por acción."""
    def permission_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = normalize_role(user.get("rol", "ciudadano"))
        permissions = set(user.get("permisos") or build_permissions_for_role(user_role))
        if required_permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Falta la autorización '{required_permission}'."
            )
        return user
    return permission_checker
