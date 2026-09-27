from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class LoteNecesidadRespuesta(LoteNecesidadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
