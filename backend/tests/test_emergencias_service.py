import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.integrations.bonita.client import BonitaClientError
from app.models import Emergencia, LoteNecesidad
from app.services.emergencias_service import EmergenciaService

VARIABLES_ESPERADAS = {
    "emergencia_id": 7,
    "nivel_gravedad": "alta",
    "zona_afectada": "Villa Urquiza",
    "descripcion_inicial": "Corte de luz",
    "lotes_json": json.dumps(
        [
            {
                "tipo": "generador",
                "cantidad": 2,
                "unidad": "unidad",
                "descripcion": "generador diesel",
            }
        ]
    ),
}


def _emergencia_con_lotes() -> Emergencia:
    lote = LoteNecesidad(
        tipo="generador",
        cantidad=2,
        unidad="unidad",
        descripcion="generador diesel",
    )
    return Emergencia(
        id=7,
        nivel_gravedad="alta",
        zona_afectada="Villa Urquiza",
        descripcion_inicial="Corte de luz",
        lotes=[lote],
    )


def _servicio_con_fakes(monkeypatch, case_id=3002, error_set=None):
    """Arma un servicio con repositorio y cliente de Bonita falsos."""
    emergencia = _emergencia_con_lotes()

    repositorio = MagicMock()
    repositorio.obtener_por_id.return_value = emergencia

    cliente = MagicMock()
    cliente.start_emergency_process = AsyncMock(return_value=case_id)
    cliente.set_case_variables = AsyncMock(
        return_value=list(VARIABLES_ESPERADAS),
        side_effect=error_set,
    )

    monkeypatch.setattr(
        "app.services.emergencias_service.bonita_client", cliente
    )

    servicio = EmergenciaService()
    servicio._repository = repositorio

    return servicio, repositorio, cliente, emergencia


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_escribe_variables_despues_de_instanciar(
    monkeypatch,
):
    """Instancia el caso y recien despues manda las 5 variables."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)

    case_id = await servicio.iniciar_proceso_bonita(MagicMock(), 7)

    assert case_id == 3002
    cliente.set_case_variables.assert_awaited_once_with(3002, VARIABLES_ESPERADAS)

    # Orden: primero instanciar, despues setear variables.
    orden = [nombre for nombre, _, _ in cliente.mock_calls]
    assert orden.index("start_emergency_process") < orden.index(
        "set_case_variables"
    )

    # Y recien ahi se persiste el caso.
    assert emergencia.bonita_case_id == "3002"
    assert json.loads(emergencia.bonita_variables_json) == VARIABLES_ESPERADAS
    repositorio.actualizar.assert_called_once()


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_no_persiste_case_id_si_falla_el_set(
    monkeypatch,
):
    """Si el seteo de variables falla, la emergencia sigue reintentable."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(
        monkeypatch,
        error_set=BonitaClientError(
            "Error seteando variable 'zona_afectada' (HTTP 500): boom"
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await servicio.iniciar_proceso_bonita(MagicMock(), 7)

    assert exc_info.value.status_code == 503
    assert "zona_afectada" in exc_info.value.detail
    # No queda un caso de Bonita huerfano registrado.
    assert emergencia.bonita_case_id is None
    assert emergencia.bonita_variables_json is None
    repositorio.actualizar.assert_not_called()


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_es_idempotente(monkeypatch):
    """Si ya hay caso, no se instancia ni se setean variables de nuevo."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    emergencia.bonita_case_id = "2999"

    case_id = await servicio.iniciar_proceso_bonita(MagicMock(), 7)

    assert case_id == 2999
    cliente.start_emergency_process.assert_not_awaited()
    cliente.set_case_variables.assert_not_awaited()
    repositorio.actualizar.assert_not_called()


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_falla_si_no_hay_lotes(monkeypatch):
    """Sin lotes no se instancia nada en Bonita."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    emergencia.lotes = []

    with pytest.raises(HTTPException) as exc_info:
        await servicio.iniciar_proceso_bonita(MagicMock(), 7)

    assert exc_info.value.status_code == 400
    cliente.start_emergency_process.assert_not_awaited()
    cliente.set_case_variables.assert_not_awaited()