import csv
import io
import json
from datetime import datetime, time, timezone
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
from ...dto.reportes_dto import (
    ActivasResueltas, CoberturaLotesReporte, ConsorciosReporte, DemandaOfertaReporte,
    EmergenciaReporte, NecesidadActual, PrioridadAbiertas, ProyectoReporte,
    RankingONGReporte, SuministroMovilizadoReporte, TiempoAdjudicacionReporte,
    TiempoPublicacionReporte, TiempoVida, ReporteBonita,
)
from ...models import Usuario
from ...services.permisos_service import AUDITOR
from ...services.reportes_service import ReportesService
from ...services.tablero_service import TableroService
from ...dto.tablero_dto import TableroRespuesta
from ...integrations.bonita.service import obtener_metricas_reporte

router = APIRouter(prefix="/reportes", tags=["Reportes"])
servicio_reportes = ReportesService()
servicio_tablero = TableroService()
auditor = Depends(requiere_roles(AUDITOR))


@router.get("/proyectos", response_model=list[ProyectoReporte], dependencies=[auditor],
            summary="(legacy) proyectos", description="(legacy) Reemplazado por GET /reportes/tablero.")
def reporte_proyectos(db: Session = Depends(get_db)):
    return servicio_reportes.proyectos(db)


@router.get("/cobertura-lotes", response_model=CoberturaLotesReporte, dependencies=[auditor],
            summary="(legacy) cobertura-lotes", description="(legacy) Reemplazado por GET /reportes/tablero.")
def reporte_cobertura_lotes(db: Session = Depends(get_db)):
    return servicio_reportes.cobertura_lotes(db)


@router.get("/tiempo-publicacion", response_model=TiempoPublicacionReporte, dependencies=[auditor],
            summary="(legacy) tiempo-publicacion", description="(legacy) Reemplazado por GET /reportes/tablero.")
def reporte_tiempo_publicacion(db: Session = Depends(get_db)):
    return servicio_reportes.tiempo_publicacion(db)


@router.get("/tiempo-adjudicacion", response_model=TiempoAdjudicacionReporte, dependencies=[auditor],
            summary="(legacy) tiempo-adjudicacion", description="(legacy) Reemplazado por GET /reportes/tablero.")
def reporte_tiempo_adjudicacion(db: Session = Depends(get_db)):
    return servicio_reportes.tiempo_adjudicacion(db)


@router.get("/bonita", response_model=ReporteBonita, dependencies=[auditor],
            summary="(legacy) bonita", description="(legacy) Reemplazado por GET /reportes/tablero.")
async def reporte_bonita() -> ReporteBonita:
    return await obtener_metricas_reporte()

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


def _utc_naive(fecha: datetime | None) -> datetime | None:
    """Fechas con zona se convierten a UTC; las fechas sin zona se toman como UTC."""
    if fecha is None or fecha.tzinfo is None:
        return fecha
    return fecha.astimezone(timezone.utc).replace(tzinfo=None)


class FiltrosReporte:
    def __init__(
        self,
        desde: datetime | None = Query(
            None,
            description="Fecha ISO inclusiva sobre la fecha de registro. Con zona horaria se convierte a UTC; sin zona se toma como UTC.",
        ),
        hasta: datetime | None = Query(
            None,
            description=(
                "Fecha ISO inclusiva sobre la fecha de registro. Si llega sin hora (YYYY-MM-DD o 00:00:00) "
                "incluye el día completo (hasta las 23:59:59.999999). Con zona horaria se convierte a UTC."
            ),
        ),
        nivel_gravedad: NivelGravedad | None = Query(None),
        formato: FormatoReporte = Query("json"),
    ) -> None:
        if hasta is not None and hasta.timetz().replace(tzinfo=None) == time(0):
            hasta = hasta.replace(hour=23, minute=59, second=59, microsecond=999999)
        desde, hasta = _utc_naive(desde), _utc_naive(hasta)
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


def _bloques_csv_tablero(tablero: dict) -> list[tuple[str, dict, list[dict]]]:
    """(nombre, metadatos, filas) por bloque del tablero, en orden de pantalla."""
    def meta(indicador: dict) -> dict:
        return {clave: indicador.get(clave) for clave in ("descripcion", "fuente", "alcance", "emergencias_incluidas")}

    resumen, recursos, proyectos, bonita = (
        tablero["resumen"], tablero["recursos"], tablero["proyectos"], tablero["bonita"]
    )
    indicadores = []
    for nombre in ("total", "abiertas", "resueltas", "prioridad_promedio_abiertas",
                   "antiguedad_abiertas_horas", "resolucion_horas"):
        dato = resumen[nombre]
        indicadores.append({
            "indicador": nombre,
            "valor": dato.get("valor", dato.get("promedio")),
            "n": dato.get("n", dato.get("valor")),
            **meta(dato),
            **({"fuente_fecha": dato["fuente_fecha"], "sin_fecha_cierre": dato["sin_fecha_cierre"]}
               if nombre == "resolucion_horas" else {}),
        })
    consorcios = proyectos["consorcios"]
    resumen_bonita = {clave: bonita[clave] for clave in (
        "disponible", "error", "casos_activos", "casos_finalizados", "casos_cancelados",
        "casos_camino_alternativo")}
    return [
        ("resumen.indicadores", {"descripcion": "Indicadores escalares del resumen", "fuente": "local+bonita",
                                 "alcance": "filtrado", "emergencias_incluidas": resumen["total"]["emergencias_incluidas"]},
         indicadores),
        ("resumen.por_estado_y_gravedad", meta(resumen["por_estado_y_gravedad"]), resumen["por_estado_y_gravedad"]["filas"]),
        ("resumen.evolucion", meta(resumen["evolucion"]), resumen["evolucion"]["filas"]),
        ("recursos.por_lote", meta(recursos["por_lote"]), recursos["por_lote"]["filas"]),
        ("recursos.totales", {**meta(recursos["totales"]), "etiqueta_recursos": recursos["etiqueta_recursos"]},
         recursos["totales"]["filas"]),
        ("proyectos.proyectos", meta(proyectos["proyectos"]), proyectos["proyectos"]["filas"]),
        ("proyectos.consorcios", meta(consorcios), [{clave: consorcios[clave] for clave in (
            "emergencias_resueltas", "resueltas_con_consorcio", "porcentaje")}]),
        ("proyectos.ranking_ongs", meta(proyectos["ranking_ongs"]), proyectos["ranking_ongs"]["filas"]),
        ("bonita.casos", meta(bonita), [resumen_bonita]),
        ("bonita.tiempos_por_etapa", meta(bonita), bonita["tiempos_por_etapa"]),
        ("bonita.verificacion", meta(bonita), bonita["verificacion"]),
    ]


def _csv_tablero(tablero: dict) -> Response:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)

    def celda(valor: object) -> object:
        if isinstance(valor, (dict, list)):
            return json.dumps(valor, ensure_ascii=False)
        return "" if valor is None else valor

    escritor.writerow(["generado_en", tablero["generado_en"]])
    escritor.writerow(["filtros", celda(tablero["filtros"])])
    for seccion, metadatos, filas in _bloques_csv_tablero(tablero):
        escritor.writerow([])
        escritor.writerow([f"SECCIÓN: {seccion}"])
        for clave, valor in metadatos.items():
            escritor.writerow([f"# {clave}", celda(valor)])
        columnas: list[str] = []
        for fila in filas:
            columnas.extend(campo for campo in fila if campo not in columnas)
        escritor.writerow(columnas)
        for fila in filas:
            escritor.writerow([celda(fila.get(columna)) for columna in columnas])
    return Response(
        content=salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reporte-completo.csv"'},
    )


@router.get(
    "/tablero",
    response_model=TableroRespuesta,
    summary="Tablero del Auditor",
    description=(
        "Resumen, recursos, proyectos y Bonita para las emergencias filtradas por fecha de registro y gravedad. "
        "Cada indicador informa descripción, fuente, alcance e ids de emergencias incluidas. "
        "Si Bonita no responde, la sección bonita viene con disponible=false y el resto responde igual."
    ),
)
async def tablero(
    filtros: FiltrosReporte = Depends(),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
) -> TableroRespuesta:
    return await servicio_tablero.obtener_tablero(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)


@router.get(
    "/exportar",
    summary="Exportar tablero",
    description="Mismo cálculo que GET /reportes/tablero: JSON idéntico o CSV con una sección por bloque (incluida Bonita).",
)
async def exportar_reporte_completo(
    filtros: FiltrosReporte = Depends(),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(AUDITOR)),
) -> object:
    datos = (await servicio_tablero.obtener_tablero(
        db, filtros.desde, filtros.hasta, filtros.nivel_gravedad
    )).model_dump(mode="json")
    if filtros.formato == "csv":
        return _csv_tablero(datos)
    return datos


@router.get("/emergencias", response_model=list[EmergenciasPorEstadoGravedad],
            summary="(legacy) emergencias", description="(legacy) Reemplazado por GET /reportes/tablero.")
def emergencias_por_estado_y_gravedad(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_emergencias(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "emergencias")


@router.get("/suministros-movilizados", response_model=list[RecursoAdjudicadoPorMes],
            summary="(legacy) suministros-movilizados", description="(legacy) Reemplazado por GET /reportes/tablero.")
def suministros_movilizados(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_suministros_movilizados(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "suministros-movilizados")


@router.get("/consorcios", response_model=ParticipacionConsorcios,
            summary="(legacy) consorcios", description="(legacy) Reemplazado por GET /reportes/tablero.")
def participacion_consorcios(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_consorcios(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "consorcios")


@router.get("/ranking-ongs", response_model=list[RankingONG],
            summary="(legacy) ranking-ongs", description="(legacy) Reemplazado por GET /reportes/tablero.")
def ranking_ongs(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_ranking_ongs(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "ranking-ongs")


@router.get("/demanda-oferta", response_model=list[DemandaOfertaRecurso],
            summary="(legacy) demanda-oferta", description="(legacy) Reemplazado por GET /reportes/tablero.")
def demanda_oferta(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_demanda_oferta(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "demanda-oferta")


@router.get("/activas-resueltas", response_model=ActivasResueltas,
            summary="(legacy) activas-resueltas", description="(legacy) Reemplazado por GET /reportes/tablero.")
def activas_resueltas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_activas_resueltas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "activas-resueltas")


@router.get("/evolucion-abiertas-resueltas", response_model=list[EvolucionEmergencias],
            summary="(legacy) evolucion-abiertas-resueltas", description="(legacy) Reemplazado por GET /reportes/tablero.")
def evolucion_abiertas_resueltas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_evolucion_abiertas_resueltas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "evolucion-abiertas-resueltas")


@router.get("/necesidades-actuales", response_model=list[NecesidadActual],
            summary="(legacy) necesidades-actuales", description="(legacy) Reemplazado por GET /reportes/tablero.")
def necesidades_actuales(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_necesidades_actuales(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "necesidades-actuales")


@router.get("/tiempo-vida", response_model=TiempoVida,
            summary="(legacy) tiempo-vida", description="(legacy) Reemplazado por GET /reportes/tablero.")
def tiempo_vida(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_tiempo_vida(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "tiempo-vida")


@router.get("/prioridad-abiertas", response_model=PrioridadAbiertas,
            summary="(legacy) prioridad-abiertas", description="(legacy) Reemplazado por GET /reportes/tablero.")
def prioridad_abiertas(filtros: FiltrosReporte = Depends(), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(AUDITOR))):
    datos = servicio_reportes.obtener_prioridad_abiertas(db, filtros.desde, filtros.hasta, filtros.nivel_gravedad)
    return _respuesta(datos, filtros, "prioridad-abiertas")
