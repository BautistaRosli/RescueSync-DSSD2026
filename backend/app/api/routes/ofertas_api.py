from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    COORDINADOR,
    ONG,
    AUDITOR,
    filtrar_organizacion,
    verificar_emergencia,
    verificar_oferta,
)
from ...database import get_db
from ...dto.ofertas_dto import (
    AdjudicacionRespuesta,
    OfertaListadoRespuesta,
    OfertaRespuesta,
    OfertasConsolidadas,
)
from ...schemas.ofertas_schema import (
    OfertaActualizar,
    OfertaCrear,
)
from ...services.ofertas_service import OfertaService

router = APIRouter(tags=["Ofertas"])

servicio_ofertas = OfertaService()


@router.get("/ofertas", response_model=list[OfertaRespuesta])
def listar_ofertas(
    emergencia_id: Optional[int] = None,
    organizacion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    return servicio_ofertas.listar_ofertas(
        db,
        emergencia_id=emergencia_id,
        organizacion_id=filtrar_organizacion(usuario, organizacion_id),
    )


@router.get("/ofertas/{oferta_id}", response_model=OfertaRespuesta)
def obtener_oferta(
    oferta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    verificar_oferta(db, usuario, oferta_id)
    return servicio_ofertas.obtener_oferta(db, oferta_id)


@router.post("/ofertas", response_model=OfertaRespuesta, status_code=201)
def crear_oferta(
    data: OfertaCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG)),
):
    organizacion_id = filtrar_organizacion(usuario, data.organizacion_id)
    verificar_emergencia(db, usuario, data.emergencia_id)
    return servicio_ofertas.crear_oferta(
        db, data.model_copy(update={"organizacion_id": organizacion_id})
    )


@router.patch("/ofertas/{oferta_id}", response_model=OfertaRespuesta)
def actualizar_oferta(
    oferta_id: int,
    data: OfertaActualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG)),
):
    verificar_oferta(db, usuario, oferta_id)
    return servicio_ofertas.actualizar_oferta(db, oferta_id, data)


@router.get(
    "/emergencias/{emergencia_id}/ofertas",
    response_model=list[OfertaListadoRespuesta],
)
def listar_ofertas_de_emergencia(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    return servicio_ofertas.listar_ofertas_de_emergencia(
        db, emergencia_id, organizacion_id=filtrar_organizacion(usuario)
    )


@router.get(
    "/emergencias/{emergencia_id}/ofertas/consolidadas",
    response_model=OfertasConsolidadas,
)
def obtener_ofertas_consolidadas(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    return servicio_ofertas.obtener_ofertas_consolidadas(db, emergencia_id)


@router.post("/ofertas/{oferta_id}/adjudicar", response_model=AdjudicacionRespuesta)
def adjudicar_oferta(
    oferta_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return servicio_ofertas.adjudicar_oferta(db, oferta_id, background_tasks)
