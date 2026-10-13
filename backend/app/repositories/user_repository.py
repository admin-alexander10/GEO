from typing import Optional
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.domain.interfaces.repositories import IUserRepository
from app.models.user import Usuario

class UserRepository(BaseRepository[Usuario], IUserRepository):
    """Repositorio especializado en operaciones de usuarios."""

    def __init__(self, db: Session):
        super().__init__(db, Usuario)

    def get_by_username(self, username: str) -> Optional[Usuario]:
        return self.db.query(Usuario).filter(Usuario.usuario == username).first()

    def get_by_link_code(self, code: str) -> Optional[Usuario]:
        return self.db.query(Usuario).filter(Usuario.codigo_enlace == code).first()

    def create_user(
        self,
        usuario: str,
        password_hash: str,
        rol: str,
        codigo_enlace: str,
        institucion: str = "individual",
        permisos: Optional[list[str]] = None,
    ) -> Usuario:
        nuevo_usuario = Usuario(
            usuario=usuario,
            password=password_hash,
            rol=rol,
            institucion=institucion,
            permisos=str(permisos or []),
            codigo_enlace=codigo_enlace,
        )
        return self.create(nuevo_usuario)
