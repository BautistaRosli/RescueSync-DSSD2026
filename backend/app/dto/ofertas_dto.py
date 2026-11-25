from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

class AporteOrganizacionRespuesta(BaseModel):
    """Cantidad del ítem aportada por cada organización participante."""

    model_config = ConfigDict(from_attributes=True)

    organizacion_id: int
    cantidad: int = Field(gt=0)


class OfertaItemRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lote_necesidad_id: int
    cantidad_ofrecida: int = Field(gt=0)
    descripcion: Optional[str] = None
    id: int
    finalizado_en: Optional[datetime] = None
    aportes: List[AporteOrganizacionRespuesta] = []


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
    adjudicada_en: Optional[datetime] = None
    organizaciones: List[OrganizacionResumen] = []
    items: List[OfertaItemRespuesta] = []


class OfertaItemListadoRespuesta(OfertaItemRespuesta):
    cantidad_verificada: Optional[int] = None


class OfertaListadoRespuesta(BaseModel):
    id: int
    emergencia_id: int
    organizacion_id: int
    organizacion_nombre: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_hora_oferta: datetime
    es_conjunta: bool = False
    adjudicada_en: Optional[datetime] = None
    organizaciones: List[OrganizacionResumen] = []
    items: List[OfertaItemListadoRespuesta] = []
    puede_seleccionar: bool = False
    estado_seleccion: Literal["sin_seleccionar", "seleccionada_para_confirmar", "adjudicada"] = "sin_seleccionar"


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


class FinalizacionOfertaRespuesta(BaseModel):
    oferta_id: int
    estado: Literal["finalizada"]
    ya_finalizada: bool = False
    tarea_bonita: Literal["Supervisar proyecto"] = "Supervisar proyecto"
    mensaje: str


class SeleccionOfertasRespuesta(BaseModel):
    emergencia_id: int
    cantidad_pares: int
    ya_confirmada: bool = False
