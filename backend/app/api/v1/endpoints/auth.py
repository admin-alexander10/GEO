from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.schemas.auth import LoginRequest, RegistroRequest, AuthResponse
from app.schemas.subscription import InstitutionInviteAcceptRequest
from app.services.auth_service import AuthService
from app.api.deps import get_auth_service, get_current_user, get_db
from app.models.user import Usuario

router = APIRouter(prefix="/auth", tags=["Autenticación"])

@router.post("/registro/", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    data: RegistroRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """Controlador de registro de nuevos usuarios en la plataforma GEORESCUE IA."""
    return auth_service.registrar_usuario(data)

@router.post("/login/", response_model=AuthResponse)
def login_usuario(
    data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """Controlador de autenticación con verificación de hash y emisión de JWT."""
    return auth_service.autenticar_usuario(data)


@router.get("/me/", response_model=AuthResponse)
def obtener_usuario_actual(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.query(Usuario).filter(Usuario.usuario == current_user["sub"]).first()
    return AuthResponse(
        mensaje="Sesión verificada.",
        usuario=account.usuario,
        rol=current_user["rol"],
        institucion=current_user["institucion"],
        permisos=current_user["permisos"],
        codigo_enlace=account.codigo_enlace,
    )


@router.post("/invitaciones/aceptar/", response_model=AuthResponse)
def aceptar_invitacion(
    data: InstitutionInviteAcceptRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    return auth_service.aceptar_invitacion(data.token, data.password)
