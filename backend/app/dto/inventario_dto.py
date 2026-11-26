from typing import Optional

from pydantic import ConfigDict

from ..schemas.inventario_schema import RecursoInventarioBase


class RecursoInventarioRespuesta(RecursoInventarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organizacion_id: int
    tipo: str
    tipo_recurso_id: Optional[int] = None
    comprometido: Optional[int] = None
    disponible: Optional[int] = None
    sincronizado: bool = False
