from pydantic import BaseModel

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
