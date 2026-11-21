from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...database import get_db
from ...dto.reportes_dto import (CoberturaLotesReporte, ConsorciosReporte, DemandaOfertaReporte,
    EmergenciaReporte, ProyectoReporte, RankingONGReporte, SuministroMovilizadoReporte,
    TiempoAdjudicacionReporte, TiempoPublicacionReporte)
from ...services.permisos_service import AUDITOR
from ...services.reportes_service import ReportesService

router = APIRouter(prefix="/reportes", tags=["Reportes"])
servicio_reportes = ReportesService()
auditor = Depends(requiere_roles(AUDITOR))


@router.get("/emergencias", response_model=list[EmergenciaReporte], dependencies=[auditor])
def reporte_emergencias(db: Session = Depends(get_db)):
    return servicio_reportes.emergencias(db)


@router.get("/suministros-movilizados", response_model=list[SuministroMovilizadoReporte], dependencies=[auditor])
def reporte_suministros_movilizados(db: Session = Depends(get_db)):
    return servicio_reportes.suministros_movilizados(db)


@router.get("/consorcios", response_model=ConsorciosReporte, dependencies=[auditor])
def reporte_consorcios(db: Session = Depends(get_db)):
    return servicio_reportes.consorcios(db)


@router.get("/proyectos", response_model=list[ProyectoReporte], dependencies=[auditor])
def reporte_proyectos(db: Session = Depends(get_db)):
    return servicio_reportes.proyectos(db)


@router.get("/cobertura-lotes", response_model=CoberturaLotesReporte, dependencies=[auditor])
def reporte_cobertura_lotes(db: Session = Depends(get_db)):
    return servicio_reportes.cobertura_lotes(db)


@router.get("/tiempo-publicacion", response_model=TiempoPublicacionReporte, dependencies=[auditor])
def reporte_tiempo_publicacion(db: Session = Depends(get_db)):
    return servicio_reportes.tiempo_publicacion(db)


@router.get("/tiempo-adjudicacion", response_model=TiempoAdjudicacionReporte, dependencies=[auditor])
def reporte_tiempo_adjudicacion(db: Session = Depends(get_db)):
    return servicio_reportes.tiempo_adjudicacion(db)


@router.get("/ranking-ongs", response_model=list[RankingONGReporte], dependencies=[auditor])
def reporte_ranking_ongs(db: Session = Depends(get_db)):
    return servicio_reportes.ranking_ongs(db)


@router.get("/demanda-oferta", response_model=list[DemandaOfertaReporte], dependencies=[auditor])
def reporte_demanda_oferta(db: Session = Depends(get_db)):
    return servicio_reportes.demanda_oferta(db)
