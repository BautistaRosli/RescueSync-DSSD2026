from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.municipio import MunicipioCreate, MunicipioRead, MunicipioUpdate
from ...services import municipio_service

router = APIRouter(prefix="/municipios", tags=["Municipios"])


@router.get("", response_model=list[MunicipioRead])
def list_municipios(db: Session = Depends(get_db)):
    return municipio_service.list_municipios(db)


@router.get("/{municipio_id}", response_model=MunicipioRead)
def get_municipio(municipio_id: int, db: Session = Depends(get_db)):
    return municipio_service.get_municipio(db, municipio_id)


@router.post("", response_model=MunicipioRead, status_code=201)
def create_municipio(data: MunicipioCreate, db: Session = Depends(get_db)):
    return municipio_service.create_municipio(db, data)


@router.patch("/{municipio_id}", response_model=MunicipioRead)
def update_municipio(
    municipio_id: int, data: MunicipioUpdate, db: Session = Depends(get_db)
):
    return municipio_service.update_municipio(db, municipio_id, data)