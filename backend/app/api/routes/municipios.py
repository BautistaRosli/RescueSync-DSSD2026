from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.emergencias.schemas import (
    MunicipioCrear,
    MunicipioRespuesta,
    MunicipioActualizar,
)
from ...domains.emergencias.service import MunicipioService

router = APIRouter(prefix="/municipios", tags=["Municipios"])

servicio_municipios = MunicipioService()


@router.get("", response_model=list[MunicipioRespuesta])
def list_municipios(db: Session = Depends(get_db)):
    return servicio_municipios.listar_municipios(db)


@router.get("/{municipio_id}", response_model=MunicipioRespuesta)
def obtener_municipio(municipio_id: int, db: Session = Depends(get_db)):
    return servicio_municipios.obtener_municipio(db, municipio_id)


@router.post("", response_model=MunicipioRespuesta, status_code=201)
def crear_municipio(data: MunicipioCrear, db: Session = Depends(get_db)):
    return servicio_municipios.crear_municipio(db, data)


@router.patch("/{municipio_id}", response_model=MunicipioRespuesta)
def actualizar_municipio(
    municipio_id: int, data: MunicipioActualizar, db: Session = Depends(get_db)
):
    return servicio_municipios.actualizar_municipio(db, municipio_id, data)
