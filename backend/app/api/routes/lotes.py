from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.lotes.schemas import (
    LoteNecesidadActualizar,
    LoteNecesidadCrear,
    LoteNecesidadRespuesta,
)
from ...domains.lotes.service import LoteService

router = APIRouter(tags=["Lotes"])

servicio_lotes = LoteService()


@router.get(
    "/emergencias/{emergencia_id}/lotes",
    response_model=list[LoteNecesidadRespuesta],
)
def listar_lotes(emergencia_id: int, db: Session = Depends(get_db)):
    return servicio_lotes.listar_lotes(db, emergencia_id)


@router.post(
    "/emergencias/{emergencia_id}/lotes",
    response_model=LoteNecesidadRespuesta,
    status_code=201,
)
def crear_lote(
    emergencia_id: int, data: LoteNecesidadCrear, db: Session = Depends(get_db)
):
    return servicio_lotes.crear_lote(db, emergencia_id, data)


@router.get("/lotes/{lote_id}", response_model=LoteNecesidadRespuesta)
def obtener_lote(lote_id: int, db: Session = Depends(get_db)):
    return servicio_lotes.obtener_lote(db, lote_id)


@router.patch("/lotes/{lote_id}", response_model=LoteNecesidadRespuesta)
def actualizar_lote(
    lote_id: int, data: LoteNecesidadActualizar, db: Session = Depends(get_db)
):
    return servicio_lotes.actualizar_lote(db, lote_id, data)


@router.delete("/lotes/{lote_id}", status_code=204)
def eliminar_lote(lote_id: int, db: Session = Depends(get_db)):
    servicio_lotes.eliminar_lote(db, lote_id)
    return Response(status_code=204)
