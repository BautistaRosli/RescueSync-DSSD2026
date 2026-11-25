"""Contrato de recepción: valida Cloud sin descartar sus campos adicionales."""

import json
from typing import Annotated, Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..dto.solicitud_evaluacion_dto import SolicitudEvaluacion

Identificador = Annotated[int, Field(strict=True, gt=0)]
Cantidad = Annotated[int, Field(strict=True, ge=0)]


class ContratoCloudCompleto(BaseModel):
    model_config = ConfigDict(extra="allow")


class CapacidadCloud(ContratoCloudCompleto):
    tipo_recurso_id: Identificador
    cantidad_ofrecida: Cantidad
    cantidad_verificada: Cantidad


class ParticipanteCloud(ContratoCloudCompleto):
    ong_id: Identificador
    rol: Literal["PRINCIPAL", "APOYO_SECUNDARIO"]
    habilitada: Annotated[bool, Field(strict=True)]
    capacidades_habilitadas: list[CapacidadCloud]


class ResultadoCloud(ContratoCloudCompleto):
    oferta_id: Identificador
    lote_id: Identificador
    es_consorcio: Annotated[bool, Field(strict=True)]
    nivel_habilitacion: Literal["COMPLETA", "PARCIAL", "SIN_DISPONIBILIDAD"]
    cantidad_ofrecida: Cantidad
    cantidad_verificada: Cantidad
    cobertura_lote_pct: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    participantes: list[ParticipanteCloud]
    observaciones: list[str]


class RespuestaCloud(ContratoCloudCompleto):
    emergencia_id: Identificador
    resultados: list[ResultadoCloud]


class RecepcionEvaluacionCloud(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solicitud_id: str = Field(min_length=1, max_length=36)
    caso_id: Identificador
    evaluacion: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def validar_json(cls, valor):
        try:
            json.dumps(valor, allow_nan=False)
        except ValueError:
            # FastAPI incluye el input en errores Pydantic; un NaN tampoco
            # puede serializarse en ese error. El rechazo HTTP evita el 500.
            raise HTTPException(422, "La evaluación debe contener JSON con números finitos") from None
        return valor

    @field_validator("evaluacion")
    @classmethod
    def validar_evaluacion(cls, valor):
        RespuestaCloud.model_validate(valor)
        return valor


class SolicitudEvaluacionPreparada(BaseModel):
    solicitud_id: str
    caso_id: Identificador
    solicitud: SolicitudEvaluacion
