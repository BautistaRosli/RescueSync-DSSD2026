from fastapi import APIRouter, Depends

from ..dependencias import requiere_roles, solo_development
from ...services.permisos_service import COORDINADOR

from ...integrations.bonita.schemas import BonitaTestVariablesRequest
from ...integrations.bonita.service import (
    setear_variables_prueba,
    verificar_conexion,
)

router = APIRouter(prefix="/bonita", tags=["Bonita"], dependencies=[
    Depends(requiere_roles(COORDINADOR)), Depends(solo_development)
])


@router.post("/test-login")
async def test_login():
    return await verificar_conexion()


@router.post("/test-variables")
async def test_variables(data: BonitaTestVariablesRequest):
    await setear_variables_prueba(data.case_id, data.variables)
    return {"ok": True}
