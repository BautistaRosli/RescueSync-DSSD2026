from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.emergencias.schemas import (
    EmergenciaActualizar,
    EmergenciaCrear,
    EmergenciaRespuesta,
)
from ...domains.emergencias.service import EmergenciaService

router = APIRouter(prefix="/emergencias", tags=["Emergencias"])

servicio_emergencias = EmergenciaService()


@router.get("", response_model=list[EmergenciaRespuesta])
def listar_emergencias(
    municipio_id: Optional[int] = None,
    publicada: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    return servicio_emergencias.listar_emergencias(
        db, municipio_id=municipio_id, publicada=publicada
    )


@router.get("/{emergencia_id}", response_model=EmergenciaRespuesta)
def obtener_emergencia(emergencia_id: int, db: Session = Depends(get_db)):
    return servicio_emergencias.obtener_emergencia(db, emergencia_id)


@router.post("", response_model=EmergenciaRespuesta, status_code=201)
def crear_emergencia(
    data: EmergenciaCrear, db: Session = Depends(get_db)
):
    return servicio_emergencias.crear_emergencia(db, data)


@router.patch("/{emergencia_id}", response_model=EmergenciaRespuesta)
def actualizar_emergencia(
    emergencia_id: int,
    data: EmergenciaActualizar,
    db: Session = Depends(get_db),
):
    return servicio_emergencias.actualizar_emergencia(
        db, emergencia_id, data
    )


@router.post("/{emergencia_id}/publicar", response_model=EmergenciaRespuesta)
def publicar_emergencia(emergencia_id: int, db: Session = Depends(get_db)):
    return servicio_emergencias.publicar_emergencia(db, emergencia_id)


@router.post("/{emergencia_id}/bonita/iniciar")
async def iniciar_proceso_bonita(
    emergencia_id: int, db: Session = Depends(get_db)
):
    case_id = await servicio_emergencias.iniciar_proceso_bonita(
        db, emergencia_id
    )
    return {"ok": True, "case_id": case_id}
