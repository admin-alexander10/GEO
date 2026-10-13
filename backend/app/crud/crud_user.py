# Wrapper de compatibilidad hacia atrás
from sqlalchemy.orm import Session
from typing import Optional
from app.models.user import Usuario
from app.schemas.auth import RegistroRequest, LoginRequest
from app.repositories.user_repository import UserRepository
from app.core.security import hash_password, verify_password, generar_codigo_enlace

def get_user_by_username(db: Session, usuario: str) -> Optional[Usuario]:
    return UserRepository(db).get_by_username(usuario)

def create_user(db: Session, user_in: RegistroRequest) -> Usuario:
    repo = UserRepository(db)
    return repo.create_user(
        usuario=user_in.usuario,
        password_hash=hash_password(user_in.password),
        rol=user_in.rol,
        institucion=user_in.institucion,
        permisos=[],
        codigo_enlace=generar_codigo_enlace(),
    )

def authenticate_user(db: Session, login_in: LoginRequest) -> Optional[Usuario]:
    usuario = get_user_by_username(db, login_in.usuario)
    if not usuario or not verify_password(login_in.password, usuario.password):
        return None
    return usuario
