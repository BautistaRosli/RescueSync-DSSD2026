from pydantic import BaseModel, Field


class EmergenciaReporte(BaseModel):
    estado: str
    nivel_gravedad: str
    cantidad: int


class SuministroMovilizadoReporte(BaseModel):
    mes: str
    tipo_recurso: str
    cantidad_adjudicada: int


class ConsorciosReporte(BaseModel):
    total_ofertas_adjudicadas: int
    ofertas_conjuntas: int
    porcentaje_consorcios: float


class ProyectoReporte(BaseModel):
    emergencia_id: int
    zona_afectada: str
    items_totales: int
    items_finalizados: int
    items_pendientes: int
    resuelta: bool


class CoberturaLoteReporte(BaseModel):
    lote_id: int
    emergencia_id: int
    tipo_recurso: str
    cantidad_requerida: int
    cantidad_ofrecida: int
    porcentaje_cobertura: float


class CoberturaLotesReporte(BaseModel):
    lotes: list[CoberturaLoteReporte]
    lotes_sin_cubrir: list[CoberturaLoteReporte]


class TiempoPublicacionReporte(BaseModel):
    promedio_horas: float
    minimo_horas: float
    maximo_horas: float


class TiempoAdjudicacionReporte(BaseModel):
    promedio_horas: float


class RankingONGReporte(BaseModel):
    organizacion_id: int
    organizacion_nombre: str
    ofertas_presentadas: int
    ofertas_adjudicadas: int
    participaciones_consorcios: int
    actividades_finalizadas: int


class DemandaOfertaReporte(BaseModel):
    tipo_recurso: str
    cantidad_pedida: int
    cantidad_ofrecida: int

from .emergencias_dto import (
    DemandaOfertaRecurso,
    EmergenciasPorEstadoGravedad,
    ParticipacionConsorcios,
    RankingONG,
    RecursoAdjudicadoPorMes,
    EvolucionEmergencias,
)


class ActivasResueltas(BaseModel):
    activas: int
    resueltas: int


class NecesidadActual(BaseModel):
    tipo_recurso: str
    tipo_recurso_id: int | None = None
    cantidad_requerida: int


class TiempoVida(BaseModel):
    promedio_horas: float


class PrioridadAbiertas(BaseModel):
    promedio_prioridad: float
    cantidad_emergencias: int


__all__ = [
    "EmergenciaReporte",
    "SuministroMovilizadoReporte",
    "ConsorciosReporte",
    "ProyectoReporte",
    "CoberturaLoteReporte",
    "CoberturaLotesReporte",
    "TiempoPublicacionReporte",
    "TiempoAdjudicacionReporte",
    "RankingONGReporte",
    "DemandaOfertaReporte",
    "DemandaOfertaRecurso",
    "EmergenciasPorEstadoGravedad",
    "ParticipacionConsorcios",
    "RankingONG",
    "RecursoAdjudicadoPorMes",
    "ActivasResueltas",
    "EvolucionEmergencias",
    "NecesidadActual",
    "TiempoVida",
    "PrioridadAbiertas",
]
