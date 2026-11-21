from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...database import get_db
from ...dto.emergencias_dto import (
    DemandaOfertaRecurso,
    EmergenciasPorEstadoGravedad,
    ParticipacionConsorcios,
    RankingONG,
    RecursoAdjudicadoPorMes,
    EvolucionEmergencias,
)
from ...dto.reportes_dto import (
    ActivasResueltas,
    NecesidadActual,
    PrioridadAbiertas,
    TiempoVida,
)
from ...models import Usuario
from ...services.permisos_service import AUDITOR
from ...services.reportes_service import ReportesService

router = APIRouter(prefix="/reportes", tags=["Reportes"])
servicio_reportes = ReportesService()


@router.get("/emergencias", response_model=list[EmergenciasPorEstadoGravedad])
def emergencias_por_estado_y_gravedad(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_reportes.obtener_emergencias(db)


@router.get(
    "/suministros-movilizados",
    response_model=list[RecursoAdjudicadoPorMes],
)
def suministros_movilizados(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_reportes.obtener_suministros_movilizados(db)


@router.get("/consorcios", response_model=ParticipacionConsorcios)
def participacion_consorcios(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_reportes.obtener_consorcios(db)


@router.get("/ranking-ongs", response_model=list[RankingONG])
def ranking_ongs(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_reportes.obtener_ranking_ongs(db)


@router.get("/demanda-oferta", response_model=list[DemandaOfertaRecurso])
def demanda_oferta(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    return servicio_reportes.obtener_demanda_oferta(db)


@router.get("/activas-resueltas", response_model=ActivasResueltas)
def activas_resueltas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    """Retorna los totales de emergencias activas y resueltas."""
    return servicio_reportes.obtener_activas_resueltas(db)


@router.get(
    "/evolucion-abiertas-resueltas",
    response_model=list[EvolucionEmergencias],
)
def evolucion_abiertas_resueltas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    """Retorna la evolución diaria de emergencias abiertas y resueltas."""
    return servicio_reportes.obtener_evolucion_abiertas_resueltas(db)


@router.get("/necesidades-actuales", response_model=list[NecesidadActual])
def necesidades_actuales(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    """Retorna la demanda agrupada de emergencias no resueltas."""
    return servicio_reportes.obtener_necesidades_actuales(db)


@router.get("/tiempo-vida", response_model=TiempoVida)
def tiempo_vida(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    """Retorna el tiempo medio de vida calculado por el dashboard."""
    return servicio_reportes.obtener_tiempo_vida(db)


@router.get("/prioridad-abiertas", response_model=PrioridadAbiertas)
def prioridad_abiertas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
):
    """Retorna la prioridad promedio de las emergencias abiertas."""
    return servicio_reportes.obtener_prioridad_abiertas(db)
