import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PATRON_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

LONGITUD_MINIMA_PASSWORD = 8

MAXIMO_BYTES_PASSWORD = 72

LONGITUD_MINIMA_NOMBRE = 2

MAXIMO_NOMBRE = 80


def validar_formato_email(valor: str) -> str:
    if not re.match(PATRON_EMAIL, valor):
        raise ValueError("El email no tiene un formato válido")
    return valor


class UsuarioCrear(BaseModel):
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
    organizacion_id: Optional[int] = None

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor: str) -> str:
        return validar_formato_email(valor)


class LoginSolicitud(BaseModel):
    email: str
    password: str = Field(
        ..., min_length=LONGITUD_MINIMA_PASSWORD, max_length=MAXIMO_BYTES_PASSWORD
    )

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor: str) -> str:
        return validar_formato_email(valor)


class OrganizacionBase(BaseModel):
    nombre: str
    tipo: str = "ong"
    email: Optional[str] = None
    telefono: Optional[str] = None
    activa: bool = True


class OrganizacionCrear(OrganizacionBase):
    cuit: Optional[str] = Field(
        default=None, description="Obligatorio para registrar una ONG en Cloud"
    )

    @model_validator(mode="after")
    def validar_datos_ong(self) -> "OrganizacionCrear":
        if self.tipo == "ong":
            if self.cuit is None or not self.cuit.strip():
                raise ValueError("El CUIT es obligatorio para registrar una ONG")
            if self.email is None:
                raise ValueError("El email de contacto es obligatorio para registrar una ONG")
            self.cuit = self.cuit.strip()
            self.email = validar_formato_email(self.email.strip())
        return self


class OrganizacionActualizar(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    activa: Optional[bool] = None
