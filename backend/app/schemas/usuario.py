import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.usuario import RolUsuario

ROLES_VALIDOS = {
    valor
    for nombre, valor in vars(RolUsuario).items()
    if not nombre.startswith("_")
}

PATRON_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

LONGITUD_MINIMA_PASSWORD = 8

MAXIMO_BYTES_PASSWORD = 72


def validar_formato_email(valor: str) -> str:
    if not re.match(PATRON_EMAIL, valor):
        raise ValueError("El email no tiene un formato válido")
    return valor


class UsuarioCreate(BaseModel):
    email: str = Field(..., max_length=150)
    password: str = Field(
        ..., min_length=LONGITUD_MINIMA_PASSWORD, max_length=MAXIMO_BYTES_PASSWORD
    )
    rol: str = RolUsuario.OPERADOR_MUNICIPAL
    municipio_id: Optional[int] = None
    organizacion_id: Optional[int] = None

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor: str) -> str:
        return validar_formato_email(valor)

    @field_validator("rol")
    @classmethod
    def rol_valido(cls, valor: str) -> str:
        if valor not in ROLES_VALIDOS:
            raise ValueError(
                f"Rol inválido. Debe ser uno de: {', '.join(sorted(ROLES_VALIDOS))}"
            )
        return valor


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    rol: str
    activo: bool
    municipio_id: Optional[int] = None
    organizacion_id: Optional[int] = None


class LoginRequest(BaseModel):
    email: str
    password: str = Field(
        ..., min_length=LONGITUD_MINIMA_PASSWORD, max_length=MAXIMO_BYTES_PASSWORD
    )

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor: str) -> str:
        return validar_formato_email(valor)
