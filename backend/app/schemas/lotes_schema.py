from typing import Optional

from pydantic import BaseModel, Field, field_validator


def validar_cantidad(valor: Optional[int]) -> Optional[int]:
    if valor is None:
        raise ValueError("cantidad no puede ser null")
    return valor


class LoteNecesidadBase(BaseModel):
    tipo: str
    cantidad: int = Field(gt=0)
    unidad: Optional[str] = None
    descripcion: Optional[str] = None


class LoteNecesidadCrear(LoteNecesidadBase):
    pass


class LoteNecesidadActualizar(BaseModel):
    tipo: Optional[str] = None
    cantidad: Optional[int] = Field(default=None, gt=0)
    unidad: Optional[str] = None
    descripcion: Optional[str] = None

    @field_validator("cantidad")
    @classmethod
    def cantidad_no_null(cls, valor: Optional[int]) -> Optional[int]:
        return validar_cantidad(valor)
