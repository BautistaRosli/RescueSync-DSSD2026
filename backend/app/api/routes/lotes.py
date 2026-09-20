from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.lote import LoteNecesidadCreate, LoteNecesidadRead, LoteNecesidadUpdate
from ...services import lote_service

router = APIRouter(tags=["Lotes"])


@router.get("/emergencias/{emergencia_id}/lotes", response_model=list[LoteNecesidadRead])
def list_lotes(emergencia_id: int, db: Session = Depends(get_db)):
    return lote_service.list_lotes(db, emergencia_id)


@router.post(
    "/emergencias/{emergencia_id}/lotes",
    response_model=LoteNecesidadRead,
    status_code=201,
)
def create_lote(
    emergencia_id: int, data: LoteNecesidadCreate, db: Session = Depends(get_db)
):
    return lote_service.create_lote(db, emergencia_id, data)


@router.get("/lotes/{lote_id}", response_model=LoteNecesidadRead)
def get_lote(lote_id: int, db: Session = Depends(get_db)):
    return lote_service.get_lote(db, lote_id)


@router.patch("/lotes/{lote_id}", response_model=LoteNecesidadRead)
def update_lote(
    lote_id: int, data: LoteNecesidadUpdate, db: Session = Depends(get_db)
):
    return lote_service.update_lote(db, lote_id, data)


@router.delete("/lotes/{lote_id}", status_code=204)
def delete_lote(lote_id: int, db: Session = Depends(get_db)):
    lote_service.delete_lote(db, lote_id)
    return Response(status_code=204)