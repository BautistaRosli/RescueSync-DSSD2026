import csv
import io
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...database import get_db
from ...dto.emergencias_dto import (
    DemandaOfertaRecurso,
    EmergenciasPorEstadoGravedad,
    EvolucionEmergencias,
    ParticipacionConsorcios,
    RankingONG,
    RecursoAdjudicadoPorMes,
)
from ...dto.reportes_dto import ActivasResueltas, NecesidadActual, PrioridadAbiertas, TiempoVida
from ...models import Usuario
from ...services.permisos_service import AUDITOR
from ...services.reportes_service import ReportesService

router = APIRouter(prefix="/reportes", tags=["Reportes"])
servicio_reportes = ReportesService()
FormatoReporte = Literal["json", "csv"]
NivelGravedad = Literal["baja", "media", "alta", "critica"]
COLUMNAS_CSV = {
    "emergencias": ["estado", "nivel_gravedad", "cantidad"],
    "suministros-movilizados": ["mes", "tipo_recurso", "tipo_recurso_id", "cantidad_adjudicada"],
    "consorcios": ["total_ofertas_adjudicadas", "ofertas_conjuntas_adjudicadas", "porcentaje_consorcios"],
    "ranking-ongs": ["organizacion_id", "organizacion_nombre", "cantidad_capacidades_asignadas"],
    "demanda-oferta": ["tipo_recurso", "tipo_recurso_id", "cantidad_requerida", "cantidad_ofrecida"],
    "activas-resueltas": ["activas", "resueltas"],
    "evolucion-abiertas-resueltas": ["fecha", "abiertas", "resueltas"],
    "necesidades-actuales": ["tipo_recurso", "tipo_recurso_id", "cantidad_requerida"],
    "tiempo-vida": ["promedio_horas"],
    "prioridad-abiertas": ["promedio_prioridad", "cantidad_emergencias"],
}
COLUMNAS_REPORTE_COMPLETO = {
    "emergencias_por_estado_y_gravedad": ["estado", "nivel_gravedad", "cantidad"],
    "recursos_adjudicados_por_mes": ["mes", "tipo_recurso", "cantidad_adjudicada"],
    "participacion_consorcios": [
        "total_ofertas_adjudicadas", "ofertas_conjuntas_adjudicadas", "porcentaje_consorcios",
    ],
    "ranking_ongs": ["organizacion_id", "organizacion_nombre", "cantidad_capacidades_asignadas"],
    "demanda_vs_oferta_por_recurso": ["tipo_recurso", "cantidad_requerida", "cantidad_ofrecida"],
    "emergencias_activas_vs_resueltas": ["activas", "resueltas"],
    "evolucion_abiertas_y_resueltas": ["fecha", "abiertas", "resueltas"],
    "necesidades_actuales": ["tipo_recurso", "cantidad_requerida"],
    "tiempo_medio_de_vida": ["promedio_horas"],
    "promedio_prioridad_abiertas": ["promedio_prioridad", "cantidad_emergencias"],
}


class FiltrosReporte:
    def __init__(
        self,
        desde: datetime | None = Query(None, description="Fecha ISO inclusiva"),
        hasta: datetime | None = Query(None, description="Fecha ISO inclusiva"),
        nivel_gravedad: NivelGravedad | None = Query(None),
        formato: FormatoReporte = Query("json"),
    ) -> None:
        if desde is not None and hasta is not None and desde > hasta:
            raise HTTPException(status_code=422, detail="El parámetro desde no puede ser posterior a hasta")
        self.desde = desde
        self.hasta = hasta
        self.nivel_gravedad = nivel_gravedad
        self.formato = formato


def _csv_response(datos: object, nombre: str) -> Response:
    if isinstance(datos, list):
        filas = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in datos]
    else:
        fila = datos.model_dump(mode="json") if hasattr(datos, "model_dump") else datos
        filas = [fila]
    filas = [fila if isinstance(fila, dict) else {"valor": fila} for fila in filas]
    campos: list[str] = list(COLUMNAS_CSV.get(nombre, []))
    for fila in filas:
        for campo in fila:
            if campo not in campos:
                campos.append(campo)
    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(salida, fieldnames=campos, extrasaction="ignore")
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({campo: json.dumps(valor, ensure_ascii=False) if isinstance(valor, (dict, list)) else valor for campo, valor in fila.items()})
    return Response(
        content=salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'},
    )


def _respuesta(datos: object, filtros: FiltrosReporte, nombre: str) -> object:
    return _csv_response(datos, nombre) if filtros.formato == "csv" else datos


def _serializar_sin_tipo_recurso_id(valor: object) -> object:
    if hasattr(valor, "model_dump"):
        return _serializar_sin_tipo_recurso_id(valor.model_dump(mode="json"))
    if isinstance(valor, dict):
        return {
            clave: _serializar_sin_tipo_recurso_id(dato)
            for clave, dato in valor.items()
            if clave != "tipo_recurso_id"
        }
    if isinstance(valor, list):
        return [_serializar_sin_tipo_recurso_id(item) for item in valor]
    return valor


def _csv_reporte_completo(datos: dict[str, object]) -> Response:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    for indice, (seccion, contenido) in enumerate(datos.items()):
        if indice:
            escritor.writerow([])
        escritor.writerow([f"SECCIÓN: {seccion}"])
        filas = contenido if isinstance(contenido, list) else [contenido]
        filas = [fila if isinstance(fila, dict) else {"valor": fila} for fila in filas]
        columnas = COLUMNAS_REPORTE_COMPLETO[seccion]
        escritor.writerow(columnas)
        for fila in filas:
            escritor.writerow([
                json.dumps(fila.get(columna), ensure_ascii=False)
                if isinstance(fila.get(columna), (dict, list))
                else fila.get(columna, "")
                for columna in columnas
            ])
    return Response(
        content=salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reporte-completo.csv"'},
    )


@router.get("/exportar")
def exportar_reporte_completo(
    filtros: FiltrosReporte = Depends(),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
) -> object:
    datos = _serializar_sin_tipo_recurso_id(
        servicio_reportes.obtener_reporte_completo(
            db, filtros.desde, filtros.hasta, filtros.nivel_gravedad
        )
    )
    if filtros.formato == "csv":
        return _csv_reporte_completo(datos)
    return datos


@router.get("/emergencias", response_model=list[EmergenciasPorEstadoGravedad])
def emergencias_por_estado_y_gravedad(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_emergencias(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "emergencias")


@router.get("/suministros-movilizados", response_model=list[RecursoAdjudicadoPorMes])
def suministros_movilizados(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_suministros_movilizados(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "suministros-movilizados")


@router.get("/consorcios", response_model=ParticipacionConsorcios)
def participacion_consorcios(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_consorcios(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "consorcios")


@router.get("/ranking-ongs", response_model=list[RankingONG])
def ranking_ongs(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_ranking_ongs(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "ranking-ongs")


@router.get("/demanda-oferta", response_model=list[DemandaOfertaRecurso])
def demanda_oferta(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_demanda_oferta(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "demanda-oferta")


@router.get("/activas-resueltas", response_model=ActivasResueltas)
def activas_resueltas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_activas_resueltas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "activas-resueltas")


@router.get("/evolucion-abiertas-resueltas", response_model=list[EvolucionEmergencias])
def evolucion_abiertas_resueltas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_evolucion_abiertas_resueltas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "evolucion-abiertas-resueltas")


@router.get("/necesidades-actuales", response_model=list[NecesidadActual])
def necesidades_actuales(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_necesidades_actuales(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "necesidades-actuales")


@router.get("/tiempo-vida", response_model=TiempoVida)
def tiempo_vida(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_tiempo_vida(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "tiempo-vida")


@router.get("/prioridad-abiertas", response_model=PrioridadAbiertas)
def prioridad_abiertas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_prioridad_abiertas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "prioridad-abiertas")
