from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.endpoints.admin import require_rotated_platform_owner
from app.schemas.directory import (
    DirectorioPublico,
    ImportacionRequest,
    ImportacionResponse,
    PuntoActualizar,
    PuntoAdmin,
    PuntoCrear,
    ResumenDirectorio,
    TipoPunto,
)
from app.services.directory_service import DirectoryService

router = APIRouter(tags=["Directorio de emergencia"])


@router.get("/directorio/emergencia", response_model=DirectorioPublico)
def directorio_de_emergencia(version: Optional[str] = None, db: Session = Depends(get_db)):
    """Directorio completo de puntos de atención locales. Es público y no recibe
    la ubicación de nadie: la app lo guarda y calcula en el dispositivo cuál queda
    más cerca. Si `version` coincide con la actual responde `sin_cambios`."""
    return DirectoryService(db).directorio_publico(version)


@router.get("/admin/directory/summary", response_model=ResumenDirectorio)
def resumen_del_directorio(_: dict = Depends(require_rotated_platform_owner), db: Session = Depends(get_db)):
    return DirectoryService(db).resumen()


@router.get("/admin/directory", response_model=List[PuntoAdmin])
def buscar_en_el_directorio(
    q: str = "",
    tipo: Optional[TipoPunto] = None,
    limit: int = 30,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    return DirectoryService(db).buscar(q, tipo, limit)


@router.post("/admin/directory", response_model=PuntoAdmin, status_code=201)
def crear_punto(payload: PuntoCrear, _: dict = Depends(require_rotated_platform_owner), db: Session = Depends(get_db)):
    return DirectoryService(db).crear(payload)


@router.patch("/admin/directory/{punto_id}", response_model=PuntoAdmin)
def corregir_punto(
    punto_id: int,
    payload: PuntoActualizar,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    return DirectoryService(db).actualizar(punto_id, payload)


@router.post("/admin/directory/import", response_model=ImportacionResponse)
def importar_directorio(
    payload: ImportacionRequest,
    _: dict = Depends(require_rotated_platform_owner),
    db: Session = Depends(get_db),
):
    """Carga o actualiza entradas desde un CSV. Las filas inválidas se informan y no se guardan."""
    return DirectoryService(db).importar(payload)
