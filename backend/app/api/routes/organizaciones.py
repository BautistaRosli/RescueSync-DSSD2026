from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.usuarios.schemas import (
    OrganizacionActualizar,
    OrganizacionCrear,
    OrganizacionRespuesta,
)
from ...domains.usuarios.service import OrganizacionService

router = APIRouter(prefix="/organizaciones", tags=["Organizaciones"])

servicio_organizaciones = OrganizacionService()


@router.get("", response_model=list[OrganizacionRespuesta])
def listar_organizaciones(db: Session = Depends(get_db)):
    return servicio_organizaciones.listar_organizaciones(db)


@router.get("/{organizacion_id}", response_model=OrganizacionRespuesta)
def obtener_organizacion(
    organizacion_id: int, db: Session = Depends(get_db)
):
    return servicio_organizaciones.obtener_organizacion(
        db, organizacion_id
    )


@router.post("", response_model=OrganizacionRespuesta, status_code=201)
def crear_organizacion(
    data: OrganizacionCrear, db: Session = Depends(get_db)
):
    return servicio_organizaciones.crear_organizacion(db, data)


@router.patch("/{organizacion_id}", response_model=OrganizacionRespuesta)
def actualizar_organizacion(
    organizacion_id: int,
    data: OrganizacionActualizar,
    db: Session = Depends(get_db),
):
    return servicio_organizaciones.actualizar_organizacion(
        db, organizacion_id, data
    )
