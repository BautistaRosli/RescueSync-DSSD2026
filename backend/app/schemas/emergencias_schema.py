from typing import Optional

from pydantic import BaseModel, Field, field_validator

from ..models import EstadoEmergencia, NivelGravedad


NIVELES_GRAVEDAD_VALIDOS = {
    valor
    for nombre, valor in vars(NivelGravedad).items()
    if not nombre.startswith("_") and isinstance(valor, str)
}

ESTADOS_EMERGENCIA_VALIDOS = {
    valor
    for nombre, valor in vars(EstadoEmergencia).items()
    if not nombre.startswith("_") and isinstance(valor, str)
}


def validar_nivel_gravedad(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        raise ValueError("nivel_gravedad no puede ser null")
    if valor not in NIVELES_GRAVEDAD_VALIDOS:
        raise ValueError(
            "nivel_gravedad debe ser uno de: "
            + ", ".join(sorted(NIVELES_GRAVEDAD_VALIDOS))
        )
    return valor


def validar_estado_emergencia(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        raise ValueError("estado no puede ser null")
    if valor not in ESTADOS_EMERGENCIA_VALIDOS:
        raise ValueError(
            "estado debe ser uno de: "
            + ", ".join(sorted(ESTADOS_EMERGENCIA_VALIDOS))
        )
    return valor


class EmergenciaBase(BaseModel):
    nivel_gravedad: str
    zona_afectada: str
    descripcion_inicial: str
    tipo_desastre: Optional[str] = None


class EmergenciaCrear(EmergenciaBase):
    @field_validator("nivel_gravedad")
    @classmethod
    def nivel_gravedad_valido(cls, valor: str) -> str:
        return validar_nivel_gravedad(valor)


class EmergenciaActualizar(BaseModel):
    nivel_gravedad: Optional[str] = None
    zona_afectada: Optional[str] = None
    descripcion_inicial: Optional[str] = None
    tipo_desastre: Optional[str] = None
    estado: Optional[str] = None

    @field_validator("nivel_gravedad")
    @classmethod
    def nivel_gravedad_valido(cls, valor: Optional[str]) -> Optional[str]:
        return validar_nivel_gravedad(valor)

    @field_validator("estado")
    @classmethod
    def estado_valido(cls, valor: Optional[str]) -> Optional[str]:
        return validar_estado_emergencia(valor)
