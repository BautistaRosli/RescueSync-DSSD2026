from fastapi import APIRouter, HTTPException

from ...integrations.bonita_client import BonitaClientError, bonita_client
from ...schemas.oferta import BonitaTestVariablesRequest

router = APIRouter(prefix="/bonita", tags=["Bonita"])


@router.get("/test-login")
async def test_login():
    try:
        return await bonita_client.test_login()
    except BonitaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/test-variables")
async def test_variables(data: BonitaTestVariablesRequest):
    try:
        await bonita_client.set_case_variables(data.case_id, data.variables)
        return {"ok": True}
    except BonitaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))