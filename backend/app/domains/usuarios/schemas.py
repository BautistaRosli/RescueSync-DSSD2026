from typing import Optional

from pydantic import BaseModel, ConfigDict


class OrganizacionBase(BaseModel):
    nombre: str
    tipo: str = "ong"
    email: Optional[str] = None
    telefono: Optional[str] = None
    activa: bool = True


class OrganizacionCrear(OrganizacionBase):
    pass


class OrganizacionActualizar(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    activa: Optional[bool] = None


class OrganizacionRespuesta(OrganizacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
