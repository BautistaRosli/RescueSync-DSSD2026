from typing import List, Optional

from pydantic import BaseModel, Field


class OfertaItemBase(BaseModel):
    lote_necesidad_id: int
    cantidad_ofrecida: int = Field(gt=0)
    descripcion: Optional[str] = None


class OfertaCrear(BaseModel):
    emergencia_id: int
    organizacion_id: int
    observaciones: Optional[str] = None
    items: List[OfertaItemBase] = []
    organizaciones_ids: List[int] = []
    es_conjunta: bool = False


class OfertaActualizar(BaseModel):
    observaciones: Optional[str] = None
    items: Optional[List[OfertaItemBase]] = None
    organizaciones_ids: Optional[List[int]] = None
    es_conjunta: Optional[bool] = None
