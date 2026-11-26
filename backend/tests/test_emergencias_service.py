import json
from unittest.mock import AsyncMock, MagicMock, call

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


def _servicio_con_fakes(monkeypatch, case_id=3002):
    """Arma un servicio con repositorio y cliente de Bonita falsos."""
    emergencia = _emergencia_con_lotes()

    repositorio = MagicMock()
    repositorio.obtener_por_id.return_value = emergencia

    cliente = MagicMock()
    cliente.start_emergency_process = AsyncMock(return_value=case_id)
    cliente.set_case_variables = AsyncMock()

    monkeypatch.setattr(
        "app.services.emergencias_service.bonita_client", cliente
    )

    servicio = EmergenciaService()
    servicio._repository = repositorio

    return servicio, repositorio, cliente, emergencia


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_envia_variables_en_el_contrato_antes_de_persistir(
    monkeypatch,
):
    """El contrato inicializa las cinco variables antes de registrar el caso."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    db = MagicMock()
    orden = []

    async def instanciar(variables):
        assert variables == VARIABLES_ESPERADAS
        assert emergencia.bonita_case_id is None
        assert emergencia.bonita_variables_json is None
        repositorio.actualizar.assert_not_called()
        orden.append("instanciar")
        return 3002

    def persistir(sesion, entidad):
        assert sesion is db and entidad is emergencia
        assert entidad.bonita_case_id == "3002"
        assert json.loads(entidad.bonita_variables_json) == VARIABLES_ESPERADAS
        orden.append("persistir")

    cliente.start_emergency_process.side_effect = instanciar
    repositorio.actualizar.side_effect = persistir

    case_id = await servicio.iniciar_proceso_bonita(db, 7)

    assert case_id == 3002
    cliente.start_emergency_process.assert_awaited_once_with(VARIABLES_ESPERADAS)
    cliente.set_case_variables.assert_not_awaited()
    assert orden == ["instanciar", "persistir"]
    assert emergencia.bonita_case_id == "3002"
    assert json.loads(emergencia.bonita_variables_json) == VARIABLES_ESPERADAS
    repositorio.actualizar.assert_called_once_with(db, emergencia)


@pytest.mark.asyncio
async def test_iniciar_proceso_bonita_no_persiste_si_falla_y_permite_reintentar(
    monkeypatch,
):
    """Una instanciación fallida conserva el estado local para el reintento."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    db = MagicMock()
    cliente.start_emergency_process.side_effect = [
        BonitaClientError("Error instanciando caso (HTTP 500): boom"),
        3002,
    ]

    with pytest.raises(HTTPException) as exc_info:
        await servicio.iniciar_proceso_bonita(db, 7)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "No se pudo iniciar el proceso en Bonita: "
        "Error instanciando caso (HTTP 500): boom"
    )
    cliente.start_emergency_process.assert_awaited_once_with(VARIABLES_ESPERADAS)
    cliente.set_case_variables.assert_not_awaited()
    assert emergencia.bonita_case_id is None
    assert emergencia.bonita_variables_json is None
    repositorio.actualizar.assert_not_called()

    assert await servicio.iniciar_proceso_bonita(db, 7) == 3002
    assert cliente.start_emergency_process.await_args_list == [
        call(VARIABLES_ESPERADAS), call(VARIABLES_ESPERADAS)
    ]
    cliente.set_case_variables.assert_not_awaited()
    assert emergencia.bonita_case_id == "3002"
    assert json.loads(emergencia.bonita_variables_json) == VARIABLES_ESPERADAS
    repositorio.actualizar.assert_called_once_with(db, emergencia)


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
async def test_iniciar_proceso_bonita_acepta_lotes_vacios(monkeypatch):
    """La creación inicial puede iniciar el caso antes de cargar los lotes."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    emergencia.lotes = []
    variables = {**VARIABLES_ESPERADAS, "lotes_json": "[]"}
    db = MagicMock()

    assert await servicio.iniciar_proceso_bonita(db, 7) == 3002

    cliente.start_emergency_process.assert_awaited_once_with(variables)
    cliente.set_case_variables.assert_not_awaited()
    assert emergencia.bonita_case_id == "3002"
    assert json.loads(emergencia.bonita_variables_json) == variables
    repositorio.actualizar.assert_called_once_with(db, emergencia)


def test_publicar_emergencia_falla_si_no_hay_lotes(monkeypatch):
    """La publicación sí exige lotes, aunque ya exista el caso de Bonita."""
    servicio, repositorio, cliente, emergencia = _servicio_con_fakes(monkeypatch)
    emergencia.lotes = []
    emergencia.publicada = False
    emergencia.bonita_case_id = "3002"

    with pytest.raises(HTTPException) as exc_info:
        servicio.publicar_emergencia(MagicMock(), 7)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "La emergencia no tiene lotes de necesidad cargados: no se puede publicar"
    )
    assert emergencia.publicada is False
    assert emergencia.fecha_publicacion is None
    assert emergencia.bonita_case_id == "3002"
    repositorio.actualizar.assert_not_called()
    cliente.start_emergency_process.assert_not_awaited()
    cliente.set_case_variables.assert_not_awaited()
