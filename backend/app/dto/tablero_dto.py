"""Contrato de salida del tablero del Auditor (pantalla y exportación)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

Alcance = Literal["filtrado", "global"]
EstadoBonita = Literal["activo", "completed", "cancelado", "no_encontrado"]


class Indicador(BaseModel):
    """Metadatos comunes: qué mide, de dónde sale y qué emergencias lo componen."""

    descripcion: str
    fuente: str  # "local", "cloud", "bonita" o combinación ("local+bonita").
    alcance: Alcance
    emergencias_incluidas: list[int]


# ---------- resumen ----------

class IndicadorConteo(Indicador):
    valor: int


class FilaEstadoGravedad(BaseModel):
    estado: str
    nivel_gravedad: str
    cantidad: int


class IndicadorEstadoGravedad(Indicador):
    filas: list[FilaEstadoGravedad]


class IndicadorPromedioValor(Indicador):
    valor: Optional[float]
    n: int


class IndicadorPromedioHoras(Indicador):
    promedio: Optional[float]
    n: int


class FuenteFechaCierre(BaseModel):
    local: int
    bonita: int


class IndicadorResolucion(IndicadorPromedioHoras):
    fuente_fecha: FuenteFechaCierre
    sin_fecha_cierre: list[int]


class FilaEvolucion(BaseModel):
    fecha: str
    aperturas: int
    cierres: int


class IndicadorEvolucion(Indicador):
    filas: list[FilaEvolucion]


class ResumenTablero(BaseModel):
    total: IndicadorConteo
    abiertas: IndicadorConteo
    resueltas: IndicadorConteo
    por_estado_y_gravedad: IndicadorEstadoGravedad
    prioridad_promedio_abiertas: IndicadorPromedioValor
    antiguedad_abiertas_horas: IndicadorPromedioHoras
    resolucion_horas: IndicadorResolucion
    evolucion: IndicadorEvolucion


# ---------- recursos ----------

class RecursoPorLote(BaseModel):
    lote_id: int
    emergencia_id: int
    tipo_recurso: str
    tipo_recurso_id: Optional[int]
    unidad: Optional[str]
    pedido: int
    ofertado: int
    verificado: Optional[int]
    cubierto_confirmado: int
    porcentaje_cobertura: Optional[float]


class IndicadorRecursosPorLote(Indicador):
    filas: list[RecursoPorLote]


class TotalRecursoMes(BaseModel):
    mes: Optional[str]
    tipo_recurso: str
    tipo_recurso_id: Optional[int]
    unidad: Optional[str]
    ofertado: int
    verificado: int
    reservado: int
    entregado: int


class IndicadorTotalesRecursos(Indicador):
    filas: list[TotalRecursoMes]


class RecursosTablero(BaseModel):
    por_lote: IndicadorRecursosPorLote
    totales: IndicadorTotalesRecursos
    etiqueta_recursos: Literal["Recursos entregados", "Recursos reservados"]


# ---------- proyectos ----------

class CantidadPorUnidad(BaseModel):
    tipo_recurso: str
    unidad: Optional[str]
    confirmado: int
    entregado: int


class ProyectoTablero(BaseModel):
    emergencia_id: int
    zona_afectada: str
    estado: Optional[str]
    bonita_case_id: Optional[str]
    items_totales: int
    items_finalizados: int
    cantidades: list[CantidadPorUnidad]
    resuelta: bool
    resolucion_horas: Optional[float]


class IndicadorProyectos(Indicador):
    filas: list[ProyectoTablero]


class IndicadorConsorcios(Indicador):
    emergencias_resueltas: int
    resueltas_con_consorcio: int
    porcentaje: Optional[float]


class FilaRankingONG(BaseModel):
    organizacion_id: int
    organizacion_nombre: str
    tipo_recurso: str
    unidad: Optional[str]
    cantidad_confirmada: float


class IndicadorRankingONG(Indicador):
    filas: list[FilaRankingONG]


class ProyectosTablero(BaseModel):
    proyectos: IndicadorProyectos
    consorcios: IndicadorConsorcios
    ranking_ongs: IndicadorRankingONG


# ---------- bonita ----------

class TiempoEtapa(BaseModel):
    etapa: str
    promedio_horas: Optional[float]
    n: int


class VerificacionCaso(BaseModel):
    emergencia_id: int
    bonita_case_id: str
    estado_local: Optional[str]
    estado_bonita: EstadoBonita
    resolucion_horas: Optional[float]


class BonitaTablero(Indicador):
    disponible: bool
    error: Optional[str]
    casos_activos: int
    casos_finalizados: int
    casos_cancelados: int
    tiempos_por_etapa: list[TiempoEtapa]
    casos_camino_alternativo: int
    verificacion: list[VerificacionCaso]


# ---------- raíz ----------

class FiltrosAplicados(BaseModel):
    desde: Optional[datetime]
    hasta: Optional[datetime]
    nivel_gravedad: Optional[str]


class TableroRespuesta(BaseModel):
    generado_en: datetime
    filtros: FiltrosAplicados
    resumen: ResumenTablero
    recursos: RecursosTablero
    proyectos: ProyectosTablero
    bonita: BonitaTablero
