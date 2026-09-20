from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.organizacion import (
    OrganizacionCreate,
    OrganizacionRead,
    OrganizacionUpdate,
)
from ...services import organizacion_service

router = APIRouter(prefix="/organizaciones", tags=["Organizaciones"])


@router.get("", response_model=list[OrganizacionRead])
def list_organizaciones(db: Session = Depends(get_db)):
    return organizacion_service.list_organizaciones(db)


@router.get("/{organizacion_id}", response_model=OrganizacionRead)
def get_organizacion(
    organizacion_id: int, db: Session = Depends(get_db)
):
    return organizacion_service.get_organizacion(db, organizacion_id)


@router.post("", response_model=OrganizacionRead, status_code=201)
def create_organizacion(
    data: OrganizacionCreate, db: Session = Depends(get_db)
):
    return organizacion_service.create_organizacion(db, data)


@router.patch("/{organizacion_id}", response_model=OrganizacionRead)
def update_organizacion(
    organizacion_id: int,
    data: OrganizacionUpdate,
    db: Session = Depends(get_db),
):
    return organizacion_service.update_organizacion(
        db, organizacion_id, data
    )