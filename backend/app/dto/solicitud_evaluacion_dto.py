"""Contrato de salida compatible con SolicitudEvaluacion de la API nacional."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Positivo = Annotated[int, Field(ge=1)]


class ContratoCloud(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoteSolicitado(ContratoCloud):
    lote_id: Positivo
    tipo_recurso_id: Positivo
    cantidad_requerida: Positivo


class ItemOfrecido(ContratoCloud):
    tipo_recurso_id: Positivo
    cantidad: Positivo


class AporteOng(ContratoCloud):
    ong_id: Positivo
    items: list[ItemOfrecido] = Field(min_length=1)


class OfertaParaEvaluacion(ContratoCloud):
    oferta_id: Positivo
    lote_id: Positivo
    ong_responsable_id: Positivo
    aportes: list[AporteOng] = Field(min_length=1)


class SolicitudEvaluacion(ContratoCloud):
    emergencia_id: Positivo
    lotes: list[LoteSolicitado] = Field(min_length=1)
    ofertas: list[OfertaParaEvaluacion]
