from pydantic import ConfigDict

from ..schemas.lotes_schema import LoteNecesidadBase


class LoteNecesidadRespuesta(LoteNecesidadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
