from typing import Optional

from pydantic import BaseModel, Field


class RecursoInventarioBase(BaseModel):
    tipo: str
    cantidad_total: int = Field(gt=0)
    unidad: Optional[str] = None
    descripcion: Optional[str] = None


class RecursoInventarioCrear(RecursoInventarioBase):
    pass


class RecursoInventarioActualizar(RecursoInventarioBase):
    pass
