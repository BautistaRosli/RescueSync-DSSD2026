from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..schemas.emergencias_schema import EmergenciaBase
from .lotes_dto import LoteNecesidadRespuesta


class EmergenciaRespuesta(EmergenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora_registro: datetime
    publicada: bool
    fecha_publicacion: Optional[datetime] = None
    estado: Optional[str] = None
    bonita_case_id: Optional[str] = None
    bonita_variables_json: Optional[str] = None
    prioridad: Optional[int] = None
    lotes: list[LoteNecesidadRespuesta] = []


class EmergenciasPaginadas(BaseModel):
    """Sobre paginado de la bandeja de emergencias del Centro Coordinador."""

    items: list[EmergenciaRespuesta] = []
    pagina: int
    por_pagina: int
    total: int
    paginas: int


class RankingONG(BaseModel):
    organizacion_id: int
    organizacion_nombre: str
    cantidad_capacidades_asignadas: int


class ParticipacionConsorcios(BaseModel):
    total_ofertas_adjudicadas: int
    ofertas_conjuntas_adjudicadas: int
    porcentaje_consorcios: float


class RecursoAdjudicadoPorMes(BaseModel):
    mes: str
    tipo_recurso: str
    tipo_recurso_id: Optional[int] = None
    cantidad_adjudicada: int


class DemandaOfertaRecurso(BaseModel):
    tipo_recurso: str
    tipo_recurso_id: Optional[int] = None
    cantidad_requerida: int
    cantidad_ofrecida: int


class EmergenciasPorEstadoGravedad(BaseModel):
    estado: str
    nivel_gravedad: str
    cantidad: int


class EvolucionEmergencias(BaseModel):
    """Estado actual agrupado por fecha de registro; no existe fecha de resolución."""

    fecha: str
    abiertas: int
    resueltas: int


class EmergenciasDashboard(BaseModel):
    total: int
    conteos_por_estado: dict[str, int]
    emergencias_activas: int
    emergencias_resueltas: int
    evolucion_abiertas_resueltas: list[EvolucionEmergencias] = []
    ranking_ongs: list[RankingONG] = []
    cantidad_total_necesidades: int
    tiempo_medio_vida_horas: float
    emergencias: list[EmergenciaRespuesta] = []
    participacion_consorcios: ParticipacionConsorcios
    recursos_adjudicados_por_mes: list[RecursoAdjudicadoPorMes] = []
    demanda_vs_oferta_por_recurso: list[DemandaOfertaRecurso] = []
    emergencias_por_estado_y_gravedad: list[EmergenciasPorEstadoGravedad] = []
