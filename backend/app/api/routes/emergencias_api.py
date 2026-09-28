from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...dto.emergencias_dto import EmergenciaRespuesta, EmergenciasPaginadas
from ...schemas.emergencias_schema import (
    EmergenciaActualizar,
    EmergenciaCrear,
)
from ...services.emergencias_service import EmergenciaService

router = APIRouter(prefix="/emergencias", tags=["Emergencias"])

servicio_emergencias = EmergenciaService()

POR_PAGINA_MAXIMO = 10


@router.get("", response_model=list[EmergenciaRespuesta])
def listar_emergencias(
    publicada: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    return servicio_emergencias.listar_emergencias(
        db, publicada=publicada
    )


@router.get("/bandeja", response_model=EmergenciasPaginadas)
def listar_bandeja_emergencias(
    publicada: bool,
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(
        default=POR_PAGINA_MAXIMO, ge=1, le=POR_PAGINA_MAXIMO
    ),
    db: Session = Depends(get_db),
):
    """Bandeja del Centro Coordinador, paginada por bucket de publicacion."""
    return servicio_emergencias.listar_emergencias_paginadas(
        db, publicada=publicada, pagina=pagina, por_pagina=por_pagina
    )


@router.get("/{emergencia_id}", response_model=EmergenciaRespuesta)
def obtener_emergencia(emergencia_id: int, db: Session = Depends(get_db)):
    return servicio_emergencias.obtener_emergencia(db, emergencia_id)


@router.post("", response_model=EmergenciaRespuesta, status_code=201)
def crear_emergencia(
    data: EmergenciaCrear,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return servicio_emergencias.crear_emergencia(
        db, data, background_tasks=background_tasks
    )


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
