"""Verifica el escaneo de cierres y la resolución explícita."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations import cloud_client
from app.integrations.bonita.client import BonitaClientError, bonita_client
from app.models import Emergencia, EstadoEmergencia
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno, estado


RUTA_SINCRONIZAR = "/api/v1/emergencias/sincronizar-cierres"
RUTA_RESOLVER = "/api/v1/emergencias/2/resolver"


def preparar_emergencia(sesiones):
    with sesiones() as db:
        emergencia = db.get(Emergencia, 2)
        emergencia.estado = EstadoEmergencia.EN_PROCESO
        emergencia.bonita_case_id = "42"
        db.commit()


def test_sincronizar_consulta_bonita_sin_liberar_cloud_ni_cambiar_estado(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    consulta = AsyncMock(return_value={"42"})
    liberar = Mock(side_effect=AssertionError("No debe liberar recursos"))
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consulta)
    monkeypatch.setattr(cloud_client, "liberar_emergencia", liberar)

    respuesta = cliente.post(RUTA_SINCRONIZAR, headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"emergencias_resueltas": [2]}
    consulta.assert_awaited_once_with({"42"})
    liberar.assert_not_called()
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


def test_sincronizar_no_muta_si_bonita_falla(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    monkeypatch.setattr(
        bonita_client,
        "obtener_casos_completados",
        AsyncMock(side_effect=BonitaClientError("sin conexión")),
    )
    anterior = estado(sesiones)

    respuesta = cliente.post(RUTA_SINCRONIZAR, headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 503
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("rol", [OPERADOR, ONG, AUDITOR, None])
def test_sincronizar_restringido_a_coordinador(entorno, monkeypatch, rol):
    cliente, sesiones, _ = entorno
    consulta = AsyncMock(return_value={"42"})
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consulta)
    anterior = estado(sesiones)

    respuesta = cliente.post(RUTA_SINCRONIZAR, headers=cabecera(rol) if rol else {})

    assert respuesta.status_code == (403 if rol else 401)
    assert estado(sesiones) == anterior
    consulta.assert_not_awaited()


def test_resolver_cambia_estado(entorno):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)

    respuesta = cliente.post(RUTA_RESOLVER, headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == EstadoEmergencia.RESUELTA
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.RESUELTA


@pytest.mark.parametrize("rol", [OPERADOR, ONG, None])
def test_resolver_requiere_coordinador_o_auditor(entorno, rol):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    anterior = estado(sesiones)

    respuesta = cliente.post(RUTA_RESOLVER, headers=cabecera(rol) if rol else {})

    assert respuesta.status_code == (403 if rol else 401)
    assert estado(sesiones) == anterior


def test_auditor_puede_resolver(entorno):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)

    respuesta = cliente.post(RUTA_RESOLVER, headers=cabecera(AUDITOR))

    assert respuesta.status_code == 200, respuesta.text
