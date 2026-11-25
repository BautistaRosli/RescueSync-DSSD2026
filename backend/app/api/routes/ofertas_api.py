from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    COORDINADOR,
    ONG,
    OPERADOR,
    AUDITOR,
    filtrar_organizacion,
    verificar_emergencia,
    verificar_oferta,
)
from ...database import get_db
from ...dto.ofertas_dto import (
    AdjudicacionRespuesta,
    OfertaItemRespuesta,
    OfertaListadoRespuesta,
    OfertaRespuesta,
    OfertasConsolidadas,
    SeleccionOfertasRespuesta,
)
from ...schemas.ofertas_schema import (
    OfertaActualizar,
    OfertaCrear,
)
from ...services.ofertas_service import OfertaService
from ...services.solicitud_evaluacion_service import SolicitudEvaluacionService
from ...services.seleccion_ofertas_service import SeleccionOfertasService
from ...dto.solicitud_evaluacion_dto import SolicitudEvaluacion
from ...schemas.evaluacion_cloud_schema import RecepcionEvaluacionCloud, SolicitudEvaluacionPreparada
from ...services.evaluacion_cloud_service import EvaluacionCloudService

router = APIRouter(tags=["Ofertas"])

servicio_ofertas = OfertaService()


@router.post("/emergencias/{emergencia_id}/solicitud-evaluacion", response_model=SolicitudEvaluacionPreparada)
def preparar_solicitud_evaluacion(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    """Prepara una ronda correlacionada; los reintentos conservan el mismo token."""
    verificar_emergencia(db, usuario, emergencia_id)
    return SolicitudEvaluacionService().preparar(db, emergencia_id)


@router.post("/emergencias/{emergencia_id}/evaluacion-cloud", status_code=204)
def recibir_evaluacion_cloud(
    emergencia_id: int,
    datos: RecepcionEvaluacionCloud,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    """Conserva íntegra la respuesta Cloud del caso y ronda preparados."""
    verificar_emergencia(db, usuario, emergencia_id)
    EvaluacionCloudService().recibir(db, emergencia_id, datos)


@router.post("/emergencias/{emergencia_id}/confirmar-seleccion", response_model=SeleccionOfertasRespuesta)
async def confirmar_seleccion(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, OPERADOR, AUDITOR)),
):
    verificar_emergencia(db, usuario, emergencia_id)
    return await SeleccionOfertasService().confirmar(db, emergencia_id)


@router.get("/emergencias/{emergencia_id}/solicitud-evaluacion", response_model=SolicitudEvaluacion)
def obtener_solicitud_evaluacion(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    """Evalúa la convocatoria y la deja en espera de adjudicación.

    Se mantiene ``GET`` por compatibilidad con el proceso Bonita existente;
    una evaluación válida tiene efecto de escritura y no puede repetirse.
    """
    verificar_emergencia(db, usuario, emergencia_id)
    return SolicitudEvaluacionService().obtener(db, emergencia_id)


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
    usuario: Usuario = Depends(requiere_roles(ONG, AUDITOR)),
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
    usuario: Usuario = Depends(requiere_roles(ONG, AUDITOR)),
):
    verificar_oferta(db, usuario, oferta_id)
    return servicio_ofertas.actualizar_oferta(db, oferta_id, data)


@router.post(
    "/ofertas/{oferta_id}/items/{item_id}/finalizar",
    response_model=OfertaItemRespuesta,
)
def finalizar_item(
    oferta_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG, AUDITOR)),
):
    verificar_oferta(db, usuario, oferta_id)
    return servicio_ofertas.finalizar_item(db, oferta_id, item_id)


@router.get(
    "/emergencias/{emergencia_id}/ofertas",
    response_model=list[OfertaListadoRespuesta],
    response_model_exclude_unset=True,
)
async def listar_ofertas_de_emergencia(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    organizacion_id = filtrar_organizacion(usuario)
    if organizacion_id is None:
        return await SeleccionOfertasService().listar(db, emergencia_id)
    return await run_in_threadpool(servicio_ofertas.listar_ofertas_de_emergencia,
        db, emergencia_id, organizacion_id=organizacion_id
    )


@router.get(
    "/emergencias/{emergencia_id}/ofertas/consolidadas",
    response_model=OfertasConsolidadas,
)
def obtener_ofertas_consolidadas(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR, ONG)),
):
    return servicio_ofertas.obtener_ofertas_consolidadas(db, emergencia_id)


@router.post("/ofertas/{oferta_id}/adjudicar", response_model=AdjudicacionRespuesta)
async def adjudicar_oferta(
    oferta_id: int,
    background_tasks: BackgroundTasks,
    para_seleccion: bool = Query(False, description="Preparar una selección de ofertas antes de confirmarla en Bonita"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, OPERADOR, AUDITOR)),
):
    if para_seleccion:
        return await SeleccionOfertasService().preparar(db, oferta_id)
    return await run_in_threadpool(servicio_ofertas.adjudicar_oferta,
        db, oferta_id, background_tasks, para_seleccion=para_seleccion
    )
