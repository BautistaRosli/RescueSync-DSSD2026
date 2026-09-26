import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PATRON_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

LONGITUD_MINIMA_PASSWORD = 8

MAXIMO_BYTES_PASSWORD = 72

LONGITUD_MINIMA_NOMBRE = 2

MAXIMO_NOMBRE = 80


def validar_formato_email(valor: str) -> str:
    if not re.match(PATRON_EMAIL, valor):
        raise ValueError("El email no tiene un formato válido")
    return valor


class UsuarioCreate(BaseModel):
    email: str = Field(..., max_length=150)
    password: str = Field(
        ..., min_length=LONGITUD_MINIMA_PASSWORD, max_length=MAXIMO_BYTES_PASSWORD
    )
    nombre: str = Field(
        ..., min_length=LONGITUD_MINIMA_NOMBRE, max_length=MAXIMO_NOMBRE
    )
    apellido: str = Field(
        ..., min_length=LONGITUD_MINIMA_NOMBRE, max_length=MAXIMO_NOMBRE
    )
    rol_id: int = Field(..., gt=0)
    municipio_id: Optional[int] = None
    organizacion_id: Optional[int] = None

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor: str) -> str:
        return validar_formato_email(valor)


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    apellido: str
    rol_id: int
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
