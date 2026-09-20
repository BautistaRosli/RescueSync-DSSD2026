from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.emergencia import (
    EmergenciaCreate,
    EmergenciaRead,
    EmergenciaUpdate,
)
from ...services import emergencia_service

router = APIRouter(prefix="/emergencias", tags=["Emergencias"])


@router.get("", response_model=list[EmergenciaRead])
def list_emergencias(
    municipio_id: Optional[int] = None,
    publicada: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    return emergencia_service.list_emergencias(
        db, municipio_id=municipio_id, publicada=publicada
    )


@router.get("/{emergencia_id}", response_model=EmergenciaRead)
def get_emergencia(emergencia_id: int, db: Session = Depends(get_db)):
    return emergencia_service.get_emergencia(db, emergencia_id)


@router.post("", response_model=EmergenciaRead, status_code=201)
def create_emergencia(data: EmergenciaCreate, db: Session = Depends(get_db)):
    return emergencia_service.create_emergencia(db, data)


@router.patch("/{emergencia_id}", response_model=EmergenciaRead)
def update_emergencia(
    emergencia_id: int,
    data: EmergenciaUpdate,
    db: Session = Depends(get_db),
):
    return emergencia_service.update_emergencia(db, emergencia_id, data)


@router.post("/{emergencia_id}/publicar", response_model=EmergenciaRead)
async def publicar_emergencia(
    emergencia_id: int, db: Session = Depends(get_db)
):
    return await emergencia_service.publicar_emergencia(db, emergencia_id)