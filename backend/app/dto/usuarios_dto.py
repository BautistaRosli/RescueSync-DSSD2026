from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..schemas.usuarios_schema import OrganizacionBase


class UsuarioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    apellido: str
    rol_id: int
    activo: bool
    organizacion_id: Optional[int] = None


class AuthRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    usuario: UsuarioRespuesta


class OrganizacionRespuesta(OrganizacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RolRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
