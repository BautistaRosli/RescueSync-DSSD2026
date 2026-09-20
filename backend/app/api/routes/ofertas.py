from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.oferta import (
    OfertaAyudaCreate,
    OfertaAyudaListRead,
    OfertaAyudaRead,
    OfertaAyudaUpdate,
    OfertasConsolidadas,
)
from ...services import oferta_service

router = APIRouter(tags=["Ofertas"])


@router.get("/ofertas", response_model=list[OfertaAyudaRead])
def list_ofertas(
    emergencia_id: Optional[int] = None,
    organizacion_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return oferta_service.list_ofertas(
        db, emergencia_id=emergencia_id, organizacion_id=organizacion_id
    )


@router.get("/ofertas/{oferta_id}", response_model=OfertaAyudaRead)
def get_oferta(oferta_id: int, db: Session = Depends(get_db)):
    return oferta_service.get_oferta(db, oferta_id)


@router.post("/ofertas", response_model=OfertaAyudaRead, status_code=201)
def create_oferta(data: OfertaAyudaCreate, db: Session = Depends(get_db)):
    return oferta_service.create_oferta(db, data)


@router.patch("/ofertas/{oferta_id}", response_model=OfertaAyudaRead)
def update_oferta(
    oferta_id: int, data: OfertaAyudaUpdate, db: Session = Depends(get_db)
):
    return oferta_service.update_oferta(db, oferta_id, data)


@router.get(
    "/emergencias/{emergencia_id}/ofertas",
    response_model=list[OfertaAyudaListRead],
)
def list_ofertas_emergencia(
    emergencia_id: int, db: Session = Depends(get_db)
):
    return oferta_service.list_ofertas_emergencia(db, emergencia_id)


@router.get(
    "/emergencias/{emergencia_id}/ofertas/consolidadas",
    response_model=OfertasConsolidadas,
)
def ofertas_consolidadas(
    emergencia_id: int, db: Session = Depends(get_db)
):
    return oferta_service.list_consolidadas(db, emergencia_id)