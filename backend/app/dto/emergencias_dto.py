from datetime import datetime
from typing import Optional

from pydantic import ConfigDict

from ..schemas.emergencias_schema import EmergenciaBase
from .lotes_dto import LoteNecesidadRespuesta


class EmergenciaRespuesta(EmergenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora_registro: datetime
    publicada: bool
    fecha_publicacion: Optional[datetime] = None
    estado: Optional[str] = None
    bonita_case_id: Optional[str] = None
    bonita_variables_json: Optional[str] = None
    lotes: list[LoteNecesidadRespuesta] = []
