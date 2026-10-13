from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.domain.exceptions import DomainException, EntityNotFoundException
from app.models.family import FamilyInvitation
from app.models.user import Usuario
from app.services.base_service import BaseService
from app.repositories.family_repository import FamilyRepository
from app.schemas.family import FamilyInvitationResponse, FamiliarCreate, FamiliarResponse

class FamilyService(BaseService):
    """Servicio de gestión de la Red de Protección Familiar."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.family_repo = FamilyRepository(db)

    def agregar_familiar(self, invitante: str, data: FamiliarCreate) -> Dict[str, Any]:
        invitado = self.db.query(Usuario).filter(
            Usuario.codigo_enlace == data.codigo_invitado,
            Usuario.is_active == 1,
            Usuario.rol == "ciudadano",
        ).first()
        if not invitado:
            # Mismo mensaje para código inexistente, cuenta inactiva o institucional:
            # no se revela qué códigos existen.
            raise DomainException(
                "Ese código no corresponde a una cuenta que pueda recibir invitaciones. "
                "Pídele a tu familiar que te lo vuelva a dictar.",
                "FAMILY_ACCOUNT_NOT_ELIGIBLE",
            )
        if invitado.usuario == invitante:
            raise DomainException("Ese es tu propio código. Necesitas el código de tu familiar.", "SELF_LINK")
        ya_vinculado = self.db.query(self.family_repo.model_cls).filter(
            self.family_repo.model_cls.usuario_responsable == invitante,
            self.family_repo.model_cls.familiar_usuario == invitado.usuario,
            self.family_repo.model_cls.consentimiento_en.is_not(None),
            self.family_repo.model_cls.revocado_en.is_(None),
        ).first()
        if ya_vinculado:
            raise DomainException("Esa persona ya está en tu red familiar.", "FAMILY_ALREADY_LINKED")
        existing = self.db.query(FamilyInvitation).filter(
            FamilyInvitation.invitante_usuario == invitante,
            FamilyInvitation.invitado_usuario == invitado.usuario,
            FamilyInvitation.estado == "PENDIENTE",
        ).first()
        if existing:
            return {"id": existing.id, "estado": existing.estado}
        invitation = FamilyInvitation(
            invitante_usuario=invitante,
            invitado_usuario=invitado.usuario,
            parentesco=data.parentesco,
            estado="PENDIENTE",
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return {
            "id": invitation.id,
            "estado": invitation.estado,
        }

    def listar_familiares(self, usuario_responsable: str) -> List[FamiliarResponse]:
        familiares = self.family_repo.get_by_responsible(usuario_responsable)
        return [
            FamiliarResponse(
                id=f.id,
                usuario_responsable=f.usuario_responsable,
                nombre=f.nombre,
                parentesco=f.parentesco,
                familiar_usuario=f.familiar_usuario,
                consentimiento_en=f.consentimiento_en,
                revocado_en=f.revocado_en,
            ) for f in familiares
        ]

    def invitaciones_enviadas(self, usuario: str) -> List[FamilyInvitationResponse]:
        """Invitaciones que el usuario envió y aún no fueron respondidas."""
        return self.db.query(FamilyInvitation).filter(
            FamilyInvitation.invitante_usuario == usuario,
            FamilyInvitation.estado == "PENDIENTE",
        ).order_by(FamilyInvitation.creado_en.desc()).all()

    def invitaciones_recibidas(self, usuario: str) -> List[FamilyInvitationResponse]:
        return self.db.query(FamilyInvitation).filter(
            FamilyInvitation.invitado_usuario == usuario,
            FamilyInvitation.estado == "PENDIENTE",
        ).order_by(FamilyInvitation.creado_en.desc()).all()

    def responder_invitacion(self, usuario: str, invitation_id: int, aceptar: bool) -> Dict[str, Any]:
        invitation = self.db.query(FamilyInvitation).filter(
            FamilyInvitation.id == invitation_id,
            FamilyInvitation.invitado_usuario == usuario,
        ).with_for_update().first()
        if not invitation:
            raise EntityNotFoundException("Invitación familiar", str(invitation_id))
        if invitation.estado != "PENDIENTE":
            raise DomainException("La invitación ya fue respondida.", "FAMILY_INVITATION_CLOSED")

        now = datetime.utcnow()
        if aceptar:
            owner = self.db.query(Usuario).filter(
                Usuario.usuario == invitation.invitante_usuario,
                Usuario.is_active == 1,
                Usuario.rol == "ciudadano",
            ).first()
            if not owner:
                raise DomainException("La cuenta que invitó ya no está activa.", "FAMILY_OWNER_INACTIVE")
            self.family_repo.create_consented_member(
                usuario_responsable=invitation.invitante_usuario,
                familiar_usuario=usuario,
                nombre=usuario,
                parentesco=invitation.parentesco,
                consentimiento_en=now,
            )
            invitation.estado = "ACEPTADA"
        else:
            invitation.estado = "RECHAZADA"
        invitation.respondido_en = now
        self.db.add(invitation)
        self.db.commit()
        return {"id": invitation.id, "estado": invitation.estado}

    def revocar_vinculo(self, usuario: str, link_id: int) -> Dict[str, Any]:
        link = self.db.query(self.family_repo.model_cls).filter(
            self.family_repo.model_cls.id == link_id,
            self.family_repo.model_cls.familiar_usuario.is_not(None),
        ).first()
        if not link or usuario not in (link.usuario_responsable, link.familiar_usuario):
            raise EntityNotFoundException("Vínculo familiar", str(link_id))
        if link.revocado_en is None:
            link.revocado_en = datetime.utcnow()
            link.revocado_por = usuario
            self.db.add(link)
            self.db.commit()
        return {"id": link.id, "estado": "REVOCADO"}
