from typing import Optional

from pydantic import BaseModel, ConfigDict


class MunicipioBase(BaseModel):
    nombre: str
    provincia: Optional[str] = None
    localidad: Optional[str] = None
    contacto: Optional[str] = None


class MunicipioCreate(MunicipioBase):
    pass


class MunicipioUpdate(BaseModel):
    nombre: Optional[str] = None
    provincia: Optional[str] = None
    localidad: Optional[str] = None
    contacto: Optional[str] = None


class MunicipioRead(MunicipioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int