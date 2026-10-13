from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from app.repositories.base_repository import BaseRepository
from app.domain.interfaces.repositories import IFamilyRepository
from app.models.family import RedFamiliar

class FamilyRepository(BaseRepository[RedFamiliar], IFamilyRepository):
    """Repositorio de la Red de Protección Familiar."""

    def __init__(self, db: Session):
        super().__init__(db, RedFamiliar)

    def get_by_responsible(self, usuario_responsable: str) -> List[RedFamiliar]:
        return self.db.query(RedFamiliar).filter(
            RedFamiliar.usuario_responsable == usuario_responsable,
            RedFamiliar.familiar_usuario.is_not(None),
            RedFamiliar.consentimiento_en.is_not(None),
            RedFamiliar.revocado_en.is_(None),
        ).all()

    def create_consented_member(
        self,
        usuario_responsable: str,
        familiar_usuario: str,
        nombre: str,
        parentesco: str,
        consentimiento_en: datetime,
    ) -> RedFamiliar:
        nuevo_familiar = RedFamiliar(
            usuario_responsable=usuario_responsable,
            familiar_usuario=familiar_usuario,
            nombre=nombre,
            parentesco=parentesco,
            consentimiento_en=consentimiento_en,
        )
        self.db.add(nuevo_familiar)
        return nuevo_familiar
