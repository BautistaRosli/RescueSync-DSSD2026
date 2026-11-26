from pydantic import BaseModel, Field


class RecursoCloudCrear(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str | None = None


class RecursoCloudRespuesta(BaseModel):
    id: int = Field(gt=0)
    nombre: str = Field(min_length=1)
    descripcion: str | None = None
