from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OfertaItemBase(BaseModel):
    lote_necesidad_id: int
    cantidad_ofrecida: int = Field(gt=0)
    descripcion: Optional[str] = None


class OfertaItemRespuesta(OfertaItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OfertaCrear(BaseModel):
    emergencia_id: int
    organizacion_id: int
    observaciones: Optional[str] = None
    items: List[OfertaItemBase] = []


class OfertaActualizar(BaseModel):
    observaciones: Optional[str] = None
    items: Optional[List[OfertaItemBase]] = None


class OfertaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
    organizacion_id: int
    observaciones: Optional[str] = None
    fecha_hora_oferta: datetime
    items: List[OfertaItemRespuesta] = []


class OfertaListadoRespuesta(BaseModel):
    id: int
    emergencia_id: int
    organizacion_id: int
    organizacion_nombre: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_hora_oferta: datetime
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
