from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Organizacion
from ..schemas.organizacion import OrganizacionCreate, OrganizacionUpdate


def list_organizaciones(db: Session) -> list[Organizacion]:
    return db.query(Organizacion).order_by(Organizacion.id.asc()).all()


def get_organizacion(db: Session, organizacion_id: int) -> Organizacion:
    organizacion = db.get(Organizacion, organizacion_id)
    if organizacion is None:
        raise HTTPException(
            status_code=404, detail="Organización no encontrada"
        )
    return organizacion


def create_organizacion(
    db: Session, data: OrganizacionCreate
) -> Organizacion:
    organizacion = Organizacion(**data.model_dump())
    db.add(organizacion)
    db.commit()
    db.refresh(organizacion)
    return organizacion


def update_organizacion(
    db: Session, organizacion_id: int, data: OrganizacionUpdate
) -> Organizacion:
    organizacion = get_organizacion(db, organizacion_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(organizacion, field, value)
    db.commit()
    db.refresh(organizacion)
    return organizacion