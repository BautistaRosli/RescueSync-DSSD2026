import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dependencias import requiere_roles
from ...models import EstadoEmergencia, Usuario
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
    EvaluacionProyectoEntrada,
    EvaluacionProyectoRespuesta,
    EvaluacionProyectoConSeleccionRespuesta,
    EtapaBonita,
    SincronizacionCierresRespuesta,
)
from ...services.emergencias_service import EmergenciaService
from ...services.curso_accion_service import CursoAccionService
from ...services.evaluacion_proyecto_service import EvaluacionProyectoService
from ...schemas.registro_recursos_schema import RegistroRecursosEntrada
from ...services.registro_recursos_service import RegistroRecursosService

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
async def listar_bandeja_emergencias(
    publicada: bool,
    estado: Optional[str] = Query(default=None),
    etapa_bonita: Optional[EtapaBonita] = Query(default=None, description="Etapa real de Bonita; sólo coordinador y publicadas"),
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
    if etapa_bonita is not None:
        if usuario.rol.nombre != COORDINADOR:
            raise HTTPException(403, "Sólo el Centro Coordinador puede consultar las etapas de Bonita")
        estado_esperado = (EstadoEmergencia.ESPERA_OFERTAS if etapa_bonita == "esperando_ofertas"
                           else EstadoEmergencia.ESPERANDO_ADJUDICACION)
        if not publicada or estado not in (None, estado_esperado):
            raise HTTPException(422, "etapa_bonita requiere publicada=true y un estado compatible")
        return await servicio_emergencias.listar_bandeja_por_etapa(db, etapa_bonita, pagina, por_pagina)
    return await run_in_threadpool(servicio_emergencias.listar_emergencias_paginadas,
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


@router.post("/sincronizar-cierres", response_model=SincronizacionCierresRespuesta)
async def sincronizar_cierres(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    """Actualiza las emergencias cuyo caso asociado terminó correctamente."""
    return await servicio_emergencias.sincronizar_cierres(db)


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


@router.get("/{emergencia_id}/evaluacion-proyecto", response_model=EvaluacionProyectoConSeleccionRespuesta | EvaluacionProyectoRespuesta)
async def obtener_evaluacion_proyecto(
    emergencia_id: int,
    incluir_seleccion: bool = Query(default=False, description="Incluye si Seleccionar oferta está lista en el caso actual"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    """Consulta la tarea de evaluación pendiente del caso actual."""
    verificar_emergencia(db, usuario, emergencia_id)
    return await EvaluacionProyectoService().consultar(db, emergencia_id, incluir_seleccion=incluir_seleccion)


@router.post("/{emergencia_id}/evaluacion-proyecto", response_model=EvaluacionProyectoRespuesta, status_code=202)
async def ejecutar_evaluacion_proyecto(
    emergencia_id: int,
    data: EvaluacionProyectoEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    """Ejecuta Evaluar proyecto; su conector aplica el curso de acción."""
    verificar_emergencia(db, usuario, emergencia_id)
    return await EvaluacionProyectoService().ejecutar(db, emergencia_id, data)


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


@router.post("/{emergencia_id}/registrar-recursos", status_code=204, response_class=Response)
async def registrar_recursos(
    emergencia_id: int,
    data: RegistroRecursosEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    verificar_emergencia(db, usuario, emergencia_id)
    await RegistroRecursosService().registrar(db, emergencia_id, data)
    return Response(status_code=204)
