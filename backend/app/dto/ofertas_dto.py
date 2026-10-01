from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from ..schemas.ofertas_schema import OfertaItemBase


class OfertaItemRespuesta(OfertaItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OrganizacionResumen(BaseModel):
    """Datos mínimos de una ONG participante de una oferta."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class OfertaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
    organizacion_id: int
    observaciones: Optional[str] = None
    fecha_hora_oferta: datetime
    es_conjunta: bool = False
    organizaciones: List[OrganizacionResumen] = []
    items: List[OfertaItemRespuesta] = []


class OfertaListadoRespuesta(BaseModel):
    id: int
    emergencia_id: int
    organizacion_id: int
    organizacion_nombre: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_hora_oferta: datetime
    es_conjunta: bool = False
    organizaciones: List[OrganizacionResumen] = []
    items: List[OfertaItemRespuesta] = []


class OfertaItemConsolidado(BaseModel):
    lote_id: int
    cantidad_ofrecida: int
    descripcion: Optional[str] = None


class OfertaConsolidada(BaseModel):
    organizacion_id: int
    organizacion_nombre: str
    items: List[OfertaItemConsolidado]


class OfertasConsolidadas(BaseModel):
    emergencia_id: int
    ofertas: List[OfertaConsolidada]


class AdjudicacionRespuesta(BaseModel):
    """Resultado de adjudicar una oferta a una emergencia."""

    oferta_id: int
    mensaje: str
