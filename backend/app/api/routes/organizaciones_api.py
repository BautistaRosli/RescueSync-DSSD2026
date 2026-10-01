from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    COORDINADOR,
    ONG,
    AUDITOR,
    filtrar_organizacion,
)
from ...database import get_db
from ...dto.usuarios_dto import OrganizacionRespuesta
from ...schemas.usuarios_schema import (
    OrganizacionActualizar,
    OrganizacionCrear,
)
from ...services.usuarios_service import OrganizacionService

router = APIRouter(prefix="/organizaciones", tags=["Organizaciones"])

servicio_organizaciones = OrganizacionService()


@router.get("", response_model=list[OrganizacionRespuesta])
def listar_organizaciones(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    return servicio_organizaciones.listar_organizaciones(
        db, organizacion_id=filtrar_organizacion(usuario)
    )


@router.get("/{organizacion_id}", response_model=OrganizacionRespuesta)
def obtener_organizacion(
    organizacion_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, ONG, AUDITOR)),
):
    return servicio_organizaciones.obtener_organizacion(
        db, filtrar_organizacion(usuario, organizacion_id)
    )


@router.post("", response_model=OrganizacionRespuesta, status_code=201)
def crear_organizacion(
    data: OrganizacionCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    return servicio_organizaciones.crear_organizacion(db, data)


@router.patch("/{organizacion_id}", response_model=OrganizacionRespuesta)
def actualizar_organizacion(
    organizacion_id: int,
    data: OrganizacionActualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    return servicio_organizaciones.actualizar_organizacion(
        db, organizacion_id, data
    )
