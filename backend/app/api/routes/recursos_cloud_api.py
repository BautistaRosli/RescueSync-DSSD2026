from fastapi import APIRouter, Depends, Query, Response

from ..dependencias import requiere_roles
from ...models import Usuario
from ...schemas.recursos_cloud_schema import (
    RecursoCloudCrear,
    RecursoCloudRespuesta,
)
from ...services.permisos_service import AUDITOR, COORDINADOR
from ...services.recursos_cloud_service import RecursosCloudService

router = APIRouter(prefix="/recursos-cloud", tags=["Recursos Cloud"])
servicio_recursos_cloud = RecursosCloudService()


@router.get("", response_model=list[RecursoCloudRespuesta])
def listar_recursos_cloud(
    texto: str | None = Query(default=None),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    return servicio_recursos_cloud.listar(texto)


@router.post("", response_model=RecursoCloudRespuesta)
def crear_recurso_cloud(
    data: RecursoCloudCrear,
    response: Response,
    usuario: Usuario = Depends(requiere_roles(COORDINADOR, AUDITOR)),
):
    recurso, creado = servicio_recursos_cloud.crear(data)
    response.status_code = 201 if creado else 200
    return recurso
