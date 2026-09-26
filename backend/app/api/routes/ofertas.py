from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.ofertas.schemas import (
    OfertaActualizar,
    OfertaCrear,
    OfertaListadoRespuesta,
    OfertaRespuesta,
    OfertasConsolidadas,
)
from ...domains.ofertas.service import OfertaService

router = APIRouter(tags=["Ofertas"])

servicio_ofertas = OfertaService()


@router.get("/ofertas", response_model=list[OfertaRespuesta])
def listar_ofertas(
    emergencia_id: Optional[int] = None,
    organizacion_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return servicio_ofertas.listar_ofertas(
        db, emergencia_id=emergencia_id, organizacion_id=organizacion_id
    )


@router.get("/ofertas/{oferta_id}", response_model=OfertaRespuesta)
def obtener_oferta(oferta_id: int, db: Session = Depends(get_db)):
    return servicio_ofertas.obtener_oferta(db, oferta_id)


@router.post("/ofertas", response_model=OfertaRespuesta, status_code=201)
def crear_oferta(data: OfertaCrear, db: Session = Depends(get_db)):
    return servicio_ofertas.crear_oferta(db, data)


@router.patch("/ofertas/{oferta_id}", response_model=OfertaRespuesta)
def actualizar_oferta(
    oferta_id: int, data: OfertaActualizar, db: Session = Depends(get_db)
):
    return servicio_ofertas.actualizar_oferta(db, oferta_id, data)


@router.get(
    "/emergencias/{emergencia_id}/ofertas",
    response_model=list[OfertaListadoRespuesta],
)
def listar_ofertas_de_emergencia(
    emergencia_id: int, db: Session = Depends(get_db)
):
    return servicio_ofertas.listar_ofertas_de_emergencia(db, emergencia_id)


@router.get(
    "/emergencias/{emergencia_id}/ofertas/consolidadas",
    response_model=OfertasConsolidadas,
)
def obtener_ofertas_consolidadas(
    emergencia_id: int, db: Session = Depends(get_db)
):
    return servicio_ofertas.obtener_ofertas_consolidadas(db, emergencia_id)
