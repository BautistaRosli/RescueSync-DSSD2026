from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from ..models.emergencia import NivelGravedad
from .lote import LoteNecesidadRead

NIVELES_GRAVEDAD_VALIDOS = {
    valor
    for nombre, valor in vars(NivelGravedad).items()
    if not nombre.startswith("_") and isinstance(valor, str)
}


def validar_nivel_gravedad(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return valor
    if valor not in NIVELES_GRAVEDAD_VALIDOS:
        raise ValueError(
            "nivel_gravedad debe ser uno de: "
            + ", ".join(sorted(NIVELES_GRAVEDAD_VALIDOS))
        )
    return valor


class EmergenciaBase(BaseModel):
    municipio_id: int
    nivel_gravedad: str
    zona_afectada: str
    descripcion_inicial: str
    tipo_desastre: Optional[str] = None


class EmergenciaCreate(EmergenciaBase):
    @field_validator("nivel_gravedad")
    @classmethod
    def nivel_gravedad_valido(cls, valor: str) -> str:
        return validar_nivel_gravedad(valor)


class EmergenciaUpdate(BaseModel):
    municipio_id: Optional[int] = None
    nivel_gravedad: Optional[str] = None
    zona_afectada: Optional[str] = None
    descripcion_inicial: Optional[str] = None
    tipo_desastre: Optional[str] = None

    @field_validator("nivel_gravedad")
    @classmethod
    def nivel_gravedad_valido(cls, valor: Optional[str]) -> Optional[str]:
        return validar_nivel_gravedad(valor)


class EmergenciaRead(EmergenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora_registro: datetime
    publicada: bool
    fecha_publicacion: Optional[datetime] = None
    bonita_case_id: Optional[str] = None
    bonita_variables_json: Optional[str] = None
    lotes: list[LoteNecesidadRead] = []