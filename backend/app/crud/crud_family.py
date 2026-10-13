# Wrapper de compatibilidad hacia atrás
from sqlalchemy.orm import Session
from typing import Any, Dict, List
from app.models.family import RedFamiliar
from app.schemas.family import FamiliarCreate
from app.repositories.family_repository import FamilyRepository
from app.services.family_service import FamilyService

def add_family_member(
    db: Session,
    familiar_in: FamiliarCreate,
    invitante: str,
) -> Dict[str, Any]:
    return FamilyService(db).agregar_familiar(invitante, familiar_in)

def get_family_by_responsible(db: Session, usuario_responsable: str) -> List[RedFamiliar]:
    return FamilyRepository(db).get_by_responsible(usuario_responsable)
