from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    AUDITOR,
    COORDINADOR,
    ONG,
    filtrar_organizacion,
)
from ...database import get_db
from ...dto.inventario_dto import RecursoInventarioRespuesta
from ...schemas.inventario_schema import (
    RecursoInventarioActualizar,
    RecursoInventarioCrear,
)
from ...services.inventario_service import InventarioService

router = APIRouter(tags=["Inventario"])

servicio_inventario = InventarioService()


@router.get(
    "/organizaciones/{organizacion_id}/inventario",
    response_model=list[RecursoInventarioRespuesta],
)
def listar_recursos(
    organizacion_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG, COORDINADOR, AUDITOR)),
):
    organizacion_id = filtrar_organizacion(usuario, organizacion_id)
    return servicio_inventario.listar_recursos(db, organizacion_id)


@router.post(
    "/organizaciones/{organizacion_id}/inventario",
    response_model=RecursoInventarioRespuesta,
    status_code=201,
)
def crear_recurso(
    organizacion_id: int,
    data: RecursoInventarioCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG)),
):
    organizacion_id = filtrar_organizacion(usuario, organizacion_id)
    return servicio_inventario.crear_recurso(db, organizacion_id, data)


@router.patch(
    "/organizaciones/{organizacion_id}/inventario/{recurso_id}",
    response_model=RecursoInventarioRespuesta,
)
def actualizar_recurso(
    organizacion_id: int,
    recurso_id: int,
    data: RecursoInventarioActualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG)),
):
    organizacion_id = filtrar_organizacion(usuario, organizacion_id)
    return servicio_inventario.actualizar_recurso(
        db, organizacion_id, recurso_id, data
    )


@router.delete(
    "/organizaciones/{organizacion_id}/inventario/{recurso_id}",
    status_code=204,
)
def eliminar_recurso(
    organizacion_id: int,
    recurso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(ONG)),
):
    organizacion_id = filtrar_organizacion(usuario, organizacion_id)
    servicio_inventario.eliminar_recurso(db, organizacion_id, recurso_id)
    return Response(status_code=204)
