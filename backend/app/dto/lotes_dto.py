from pydantic import BaseModel, ConfigDict, Field


class LoteNecesidadRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo: str
    cantidad: int = Field(gt=0)
    unidad: str | None = None
    descripcion: str | None = None
    id: int
    emergencia_id: int
