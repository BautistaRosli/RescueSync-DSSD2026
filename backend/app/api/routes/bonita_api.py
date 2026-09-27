from fastapi import APIRouter

from ...integrations.bonita.schemas import BonitaTestVariablesRequest
from ...integrations.bonita.service import (
    setear_variables_prueba,
    verificar_conexion,
)

router = APIRouter(prefix="/bonita", tags=["Bonita"])


@router.get("/test-login")
async def test_login():
    return await verificar_conexion()


@router.post("/test-variables")
async def test_variables(data: BonitaTestVariablesRequest):
    await setear_variables_prueba(data.case_id, data.variables)
    return {"ok": True}
