from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..lotes.schemas import LoteNecesidadRespuesta


class MunicipioBase(BaseModel):
    nombre: str
    provincia: Optional[str] = None
    localidad: Optional[str] = None
    contacto: Optional[str] = None


class MunicipioCrear(MunicipioBase):
    pass


class MunicipioActualizar(BaseModel):
    nombre: Optional[str] = None
    provincia: Optional[str] = None
    localidad: Optional[str] = None
    contacto: Optional[str] = None


class MunicipioRespuesta(MunicipioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class EmergenciaBase(BaseModel):
    municipio_id: int
    nivel_gravedad: str
    zona_afectada: str
    descripcion_inicial: str
    tipo_desastre: Optional[str] = None


class EmergenciaCrear(EmergenciaBase):
    pass


class EmergenciaActualizar(BaseModel):
    municipio_id: Optional[int] = None
    nivel_gravedad: Optional[str] = None
    zona_afectada: Optional[str] = None
    descripcion_inicial: Optional[str] = None
    tipo_desastre: Optional[str] = None


class EmergenciaRespuesta(EmergenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora_registro: datetime
    publicada: bool
    fecha_publicacion: Optional[datetime] = None
    bonita_case_id: Optional[str] = None
    bonita_variables_json: Optional[str] = None
    lotes: list[LoteNecesidadRespuesta] = []
