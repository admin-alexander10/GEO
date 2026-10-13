from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.family import FamilyInvitationResponse, FamiliarCreate, FamiliarResponse
from app.services.family_service import FamilyService
from app.api.deps import get_family_service, require_permission

router = APIRouter(prefix="/familia", tags=["Red Familiar"])

@router.post("/agregar/", status_code=status.HTTP_201_CREATED)
def agregar_familiar(
    data: FamiliarCreate,
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    """Invita con el código de enlace del familiar. Solo hay vínculo cuando la otra cuenta acepta."""
    return family_service.agregar_familiar(user["sub"], data)

@router.get("/listar/{usuario_responsable}", response_model=List[FamiliarResponse])
def listar_familiares(
    usuario_responsable: str,
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    if usuario_responsable != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes consultar tu propia red familiar.",
        )
    return family_service.listar_familiares(usuario_responsable)


@router.get("/invitaciones/recibidas/", response_model=List[FamilyInvitationResponse])
def invitaciones_recibidas(
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    return family_service.invitaciones_recibidas(user["sub"])


@router.get("/invitaciones/enviadas/", response_model=List[FamilyInvitationResponse])
def invitaciones_enviadas(
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    return family_service.invitaciones_enviadas(user["sub"])


@router.post("/invitaciones/{invitation_id}/aceptar/")
def aceptar_invitacion(
    invitation_id: int,
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    return family_service.responder_invitacion(user["sub"], invitation_id, True)


@router.post("/invitaciones/{invitation_id}/rechazar/")
def rechazar_invitacion(
    invitation_id: int,
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    return family_service.responder_invitacion(user["sub"], invitation_id, False)


@router.post("/vinculos/{link_id}/revocar/")
def revocar_vinculo(
    link_id: int,
    family_service: FamilyService = Depends(get_family_service),
    user: dict = Depends(require_permission("family:view")),
):
    return family_service.revocar_vinculo(user["sub"], link_id)
