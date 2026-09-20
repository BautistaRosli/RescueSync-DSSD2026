from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .lote import LoteNecesidadRead


class EmergenciaBase(BaseModel):
    municipio_id: int
    nivel_gravedad: str
    zona_afectada: str
    descripcion_inicial: str
    tipo_desastre: Optional[str] = None


class EmergenciaCreate(EmergenciaBase):
    pass


class EmergenciaUpdate(BaseModel):
    municipio_id: Optional[int] = None
    nivel_gravedad: Optional[str] = None
    zona_afectada: Optional[str] = None
    descripcion_inicial: Optional[str] = None
    tipo_desastre: Optional[str] = None


class EmergenciaRead(EmergenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora_registro: datetime
    publicada: bool
    fecha_publicacion: Optional[datetime] = None
    bonita_case_id: Optional[str] = None
    bonita_variables_json: Optional[str] = None
    lotes: list[LoteNecesidadRead] = []