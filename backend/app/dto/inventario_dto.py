from pydantic import ConfigDict

from ..schemas.inventario_schema import RecursoInventarioBase


class RecursoInventarioRespuesta(RecursoInventarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organizacion_id: int
