import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    OPERADOR,
    COORDINADOR,
    ONG,
    AUDITOR,
    filtrar_publicada,
    verificar_emergencia,
)
from ...database import get_db
from ...dto.emergencias_dto import (
    EmergenciaRespuesta,
    EmergenciasDashboard,
    EmergenciasPaginadas,
)
from ...schemas.emergencias_schema import (
    EmergenciaActualizar,
    EmergenciaCrear,
    ESTADOS_EMERGENCIA_VALIDOS,
    CursoAccionEntrada,
)
from ...services.emergencias_service import EmergenciaService
from ...services.curso_accion_service import CursoAccionService

router = APIRouter(prefix="/emergencias", tags=["Emergencias"])

logger = logging.getLogger(__name__)

servicio_emergencias = EmergenciaService()

POR_PAGINA_MAXIMO = 10


@router.get("", response_model=list[EmergenciaRespuesta])
def listar_emergencias(
    publicada: Optional[bool] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(OPERADOR, COORDINADOR, ONG, AUDITOR)),
):
    return servicio_emergencias.listar_emergencias(
        db, publicada=filtrar_publicada(usuario, publicada)
    )


@router.get("/bandeja", response_model=EmergenciasPaginadas)
def listar_bandeja_emergencias(
    publicada: bool,
    estado: Optional[str] = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=POR_PAGINA_MAXIMO, ge=1, le=POR_PAGINA_MAXIMO),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(OPERADOR, COORDINADOR, ONG, AUDITOR)),
):
    """Bandeja del Centro Coordinador, paginada por bucket de publicacion."""
    if estado is not None and estado not in ESTADOS_EMERGENCIA_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=(
                "estado debe ser uno de: "
                + ", ".join(sorted(ESTADOS_EMERGENCIA_VALIDOS))
            ),
        )
    return servicio_emergencias.listar_emergencias_paginadas(
        db,
        publicada=filtrar_publicada(usuario, publicada),
        estado=estado,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get("/dashboard", response_model=EmergenciasDashboard)
def obtener_dashboard_emergencias(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_emergencias.obtener_dashboard(db)


@router.get("/{emergencia_id}", response_model=EmergenciaRespuesta)
def obtener_emergencia(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(OPERADOR, COORDINADOR, ONG, AUDITOR)),
):
    verificar_emergencia(db, usuario, emergencia_id)
    return servicio_emergencias.obtener_emergencia(db, emergencia_id)


@router.post("", response_model=EmergenciaRespuesta, status_code=201)
async def crear_emergencia(
    data: EmergenciaCrear,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(OPERADOR, AUDITOR)),
):
    respuesta = await servicio_emergencias.crear_emergencia(
        db, data, background_tasks=background_tasks
    )

    try:
        await servicio_emergencias.iniciar_proceso_bonita(db, respuesta.id)
    except HTTPException as exc:
        logger.error(
            f"No se pudo iniciar el proceso en Bonita para la emergencia "
            f"{respuesta.id}: {exc.detail}"
        )

    resultado = servicio_emergencias.obtener_emergencia(db, respuesta.id)
    resultado.prioridad = respuesta.prioridad
    return resultado


@router.patch("/{emergencia_id}", response_model=EmergenciaRespuesta)
def actualizar_emergencia(
    emergencia_id: int,
    data: EmergenciaActualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    return servicio_emergencias.actualizar_emergencia(
        db, emergencia_id, data
    )


@router.post("/{emergencia_id}/publicar", response_model=EmergenciaRespuesta)
async def publicar_emergencia(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    await servicio_emergencias.iniciar_proceso_bonita(db, emergencia_id)
    return await CursoAccionService().publicar(db, emergencia_id)


@router.post("/{emergencia_id}/curso-accion", status_code=204, response_class=Response)
def aplicar_curso_accion(
    emergencia_id: int,
    data: CursoAccionEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    """Aplica la decisión del supervisor al finalizar Evaluar proyecto.

    Usa el mismo Bearer que solicitud-evaluacion y no consulta esa tarea:
    el conector ON_FINISH todavía está ejecutándose dentro de Bonita.
    """
    verificar_emergencia(db, usuario, emergencia_id)
    CursoAccionService().aplicar(db, emergencia_id, data.accion)
    return Response(status_code=204)


@router.post("/{emergencia_id}/bonita/iniciar")
async def iniciar_proceso_bonita(
    emergencia_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    case_id = await servicio_emergencias.iniciar_proceso_bonita(
        db, emergencia_id
    )
    return {"ok": True, "case_id": case_id}
