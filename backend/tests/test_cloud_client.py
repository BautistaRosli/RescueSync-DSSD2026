"""La única identidad Cloud es la aplicación; las personas usan JWT local."""

from unittest.mock import Mock

import httpx
import pytest

from app.models import Organizacion
from app.services.permisos_service import COORDINADOR
from test_permisos_api import cabecera, entorno, estado
from test_organizaciones_cloud import ALTA_ONG, IDENTIDAD_CLOUD

TOKEN_APP = "token-opaco-exclusivo-de-la-aplicacion"
SESION_APP = {"access_token": TOKEN_APP, "token_type": "bearer", "expires_in": 3600}


@pytest.fixture
def entorno_app(entorno, monkeypatch):
    monkeypatch.setenv("CLOUD_API_URL", "https://cloud.example.test/base/")
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-aplicacion-prueba")
    remoto = Mock(side_effect=[httpx.Response(200, json=SESION_APP),
                               httpx.Response(201, json=IDENTIDAD_CLOUD)])
    monkeypatch.setattr(httpx, "post", remoto)
    return *entorno[:2], remoto


def test_ong_usa_solo_credenciales_app_y_no_reenvia_jwt_persona(entorno_app):
    cliente, sesiones, remoto = entorno_app
    encabezados = cabecera(COORDINADOR)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=encabezados)
    assert respuesta.status_code == 201, respuesta.text
    assert remoto.call_count == 2
    login, registro = remoto.call_args_list
    assert login.args == ("https://cloud.example.test/base/auth/login",)
    assert login.kwargs == {"json": {"usuario": "aplicacion-prueba", "password": "credencial-aplicacion-prueba"}, "timeout": 10.0}
    assert registro.kwargs["headers"] == {"Authorization": f"Bearer {TOKEN_APP}"}
    assert registro.kwargs["headers"] != encabezados
    assert TOKEN_APP not in respuesta.text
    with sesiones() as db:
        assert db.query(Organizacion).count() == 3


@pytest.mark.parametrize("variable", ["CLOUD_APP_USUARIO", "CLOUD_APP_PASSWORD"])
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sin_config_app_no_http_ni_escrituras(entorno_app, monkeypatch, variable, valor):
    cliente, sesiones, remoto = entorno_app
    if valor is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, valor)
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503 and estado(sesiones) == anterior
    remoto.assert_not_called()


@pytest.mark.parametrize("respuesta", [
    httpx.Response(401, json={"detail": "secreto upstream"}), httpx.Response(403),
    httpx.Response(500), httpx.Response(302), httpx.Response(201),
    httpx.Response(200, content="no-json"), httpx.Response(200, json=[]),
    httpx.Response(200, json={}),
    *[httpx.Response(200, json={**SESION_APP, "access_token": valor}) for valor in (None, 42, "", "   ")],
    *[httpx.Response(200, json={**SESION_APP, "expires_in": valor}) for valor in (True, 0, -1, "3600", 1.5)],
    httpx.Response(200, json={**SESION_APP, "token_type": "otro"}),
])
def test_login_app_invalido_es_503_y_no_crea_local(entorno_app, respuesta):
    cliente, sesiones, remoto = entorno_app
    remoto.side_effect = [respuesta]
    anterior = estado(sesiones)
    resultado = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert resultado.status_code == 503 and estado(sesiones) == anterior
    assert "secreto" not in resultado.text and "access_token" not in resultado.json()
    remoto.assert_called_once()


@pytest.mark.parametrize("error", [httpx.ReadTimeout("secreto"), httpx.ConnectError("secreto"), httpx.InvalidURL("secreto")])
def test_fallo_transporte_login_app_es_503(entorno_app, error):
    cliente, sesiones, remoto = entorno_app
    remoto.side_effect = error
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503 and "secreto" not in respuesta.text
    assert estado(sesiones) == anterior
    remoto.assert_called_once()


def test_login_por_operacion_no_cachea_sesion_app(entorno_app):
    cliente, _, remoto = entorno_app
    otro = {**ALTA_ONG, "nombre": "Otra ONG", "cuit": "30-12345678-8"}
    remoto.side_effect = [httpx.Response(200, json=SESION_APP),
        httpx.Response(201, json=IDENTIDAD_CLOUD), httpx.Response(200, json={**SESION_APP, "access_token": "nuevo-token"}),
        httpx.Response(201, json={**IDENTIDAD_CLOUD, "razon_social": otro["nombre"], "cuit": otro["cuit"]})]
    for datos in (ALTA_ONG, otro):
        assert cliente.post("/api/v1/organizaciones", json=datos, headers=cabecera(COORDINADOR)).status_code == 201
    assert remoto.call_count == 4
    assert remoto.call_args_list[3].kwargs["headers"] == {"Authorization": "Bearer nuevo-token"}
