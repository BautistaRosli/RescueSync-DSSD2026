"""Entrada del conector Registrar recursos, con la selección real del caso."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identificador = Annotated[int, Field(strict=True, gt=0)]


class ParRegistroRecursos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oferta_id: Identificador
    lote_id: Identificador


class RegistroRecursosEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caso_id: Identificador
    seleccion: list[ParRegistroRecursos] = Field(min_length=1)

    @model_validator(mode="after")
    def validar_pares_unicos(self):
        pares = {(par.oferta_id, par.lote_id) for par in self.seleccion}
        if len(pares) != len(self.seleccion):
            raise ValueError("La selección contiene pares duplicados")
        return self
