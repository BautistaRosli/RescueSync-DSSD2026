from typing import Any

from fastapi import HTTPException

from .client import BonitaClientError, bonita_client


async def verificar_conexion() -> dict:
    """Prueba de connectivity/login contra Bonita."""
    try:
        return await bonita_client.test_login()
    except BonitaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


async def setear_variables_prueba(
    case_id: int, variables: dict[str, Any]
) -> None:
    """Setea variables de prueba sobre un caso existente de Bonita."""
    try:
        await bonita_client.set_case_variables(case_id, variables)
    except BonitaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
