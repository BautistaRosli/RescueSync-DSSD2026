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
