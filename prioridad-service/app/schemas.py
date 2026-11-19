"""Contratos Pydantic del servicio de prioridad."""

from enum import Enum

from pydantic import BaseModel


class Gravedad(str, Enum):
    """Niveles de gravedad admitidos por el contrato."""

    alta = "alta"
    media = "media"
    baja = "baja"


class PrioridadRequest(BaseModel):
    """Cuerpo de entrada de POST /prioridad.

    La zona no declara ``min_length`` a propósito: el vacío se valida en la
    ruta para responder 400 (y no 422) según el contrato.
    """

    gravedad: Gravedad
    zona: str


class PrioridadResponse(BaseModel):
    """Cuerpo de salida de POST /prioridad."""

    prioridad: int
    gravedad: str
    zona: str
    timestamp: str
