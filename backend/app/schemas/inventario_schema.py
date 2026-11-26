from typing import Optional

from pydantic import BaseModel, Field


class RecursoInventarioBase(BaseModel):
    cantidad_total: int = Field(gt=0)
    unidad: Optional[str] = None
    descripcion: Optional[str] = None


class RecursoInventarioCrear(RecursoInventarioBase):
    tipo_recurso_id: int = Field(gt=0)
    # Compatibilidad con clientes viejos: el nombre sale del catálogo nacional.
    tipo: Optional[str] = None


class RecursoInventarioActualizar(RecursoInventarioBase):
    # Sólo vincula filas previas sin equivalencia nacional.
    tipo_recurso_id: Optional[int] = Field(default=None, gt=0)
