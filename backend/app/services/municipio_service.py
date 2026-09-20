from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Municipio
from ..schemas.municipio import MunicipioCreate, MunicipioUpdate


def list_municipios(db: Session) -> list[Municipio]:
    return db.query(Municipio).order_by(Municipio.id.asc()).all()


def get_municipio(db: Session, municipio_id: int) -> Municipio:
    municipio = db.get(Municipio, municipio_id)
    if municipio is None:
        raise HTTPException(status_code=404, detail="Municipio no encontrado")
    return municipio


def create_municipio(db: Session, data: MunicipioCreate) -> Municipio:
    municipio = Municipio(**data.model_dump())
    db.add(municipio)
    db.commit()
    db.refresh(municipio)
    return municipio


def update_municipio(
    db: Session, municipio_id: int, data: MunicipioUpdate
) -> Municipio:
    municipio = get_municipio(db, municipio_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(municipio, field, value)
    db.commit()
    db.refresh(municipio)
    return municipio