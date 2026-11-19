"""La única identidad Cloud es la aplicación; las personas usan JWT local."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import Mock

import httpx
import pytest

from app.integrations import cloud_client
from app.models import Organizacion
from app.services.permisos_service import COORDINADOR
from test_permisos_api import cabecera, entorno, estado
from test_organizaciones_cloud import ALTA_ONG, IDENTIDAD_CLOUD

TOKEN_APP = "token-opaco-exclusivo-de-la-aplicacion"
SESION_APP = {"access_token": TOKEN_APP, "token_type": "bearer", "expires_in": 3600}


@pytest.fixture(autouse=True)
def aislar_sesion_app(monkeypatch):
    monkeypatch.setattr(cloud_client, "_sesion_aplicacion", None, raising=False)


@pytest.fixture
def sesion_simulada(monkeypatch):
    monkeypatch.setenv("CLOUD_API_URL", "https://cloud.example.test/base/")
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-aplicacion-prueba")
    reloj = [100.0]
    monkeypatch.setattr(cloud_client, "monotonic", lambda: reloj[0], raising=False)
    login = Mock(return_value=httpx.Response(200, json=SESION_APP))
    monkeypatch.setattr(cloud_client, "solicitar", login)
    return reloj, login


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


def test_operaciones_ong_reutilizan_sesion_app_vigente(entorno_app):
    cliente, _, remoto = entorno_app
    otro = {**ALTA_ONG, "nombre": "Otra ONG", "cuit": "30-12345678-8"}
    remoto.side_effect = [httpx.Response(200, json=SESION_APP),
        httpx.Response(201, json=IDENTIDAD_CLOUD),
        httpx.Response(201, json={**IDENTIDAD_CLOUD, "razon_social": otro["nombre"], "cuit": otro["cuit"]})]
    for datos in (ALTA_ONG, otro):
        assert cliente.post("/api/v1/organizaciones", json=datos, headers=cabecera(COORDINADOR)).status_code == 201
    assert remoto.call_count == 3
    for registro in remoto.call_args_list[1:]:
        assert registro.kwargs["headers"] == {"Authorization": f"Bearer {TOKEN_APP}"}


@pytest.mark.parametrize("duracion,margen", [(10, 1.0), (3600, 30.0)])
def test_reutiliza_hasta_margen_y_renueva_en_limite(sesion_simulada, duracion, margen):
    reloj, login = sesion_simulada
    login.side_effect = [
        httpx.Response(200, json={**SESION_APP, "expires_in": duracion}),
        httpx.Response(200, json={**SESION_APP, "access_token": "token-renovado"}),
    ]
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    reloj[0] = 100.0 + duracion - margen - 0.001
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    login.assert_called_once_with("login", "aplicacion-prueba", "credencial-aplicacion-prueba")
    reloj[0] = 100.0 + duracion - margen
    assert cloud_client.obtener_token_aplicacion() == "token-renovado"
    assert cloud_client.obtener_token_aplicacion() == "token-renovado"
    assert login.call_count == 2


def test_renovacion_es_perezosa_y_no_suma_latencia_del_login(sesion_simulada):
    reloj, login = sesion_simulada

    def autenticar(*args):
        reloj[0] += 5.0
        return httpx.Response(200, json={**SESION_APP, "expires_in": 100})

    login.side_effect = autenticar
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    reloj[0] = 190.0
    assert login.call_count == 1
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    assert login.call_count == 2
    reloj[0] = 1000.0
    assert login.call_count == 2
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    assert login.call_count == 3


@pytest.mark.parametrize("vencido", [False, True])
def test_operaciones_simultaneas_comparten_un_solo_login(sesion_simulada, vencido):
    reloj, login = sesion_simulada
    if vencido:
        assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
        reloj[0] += SESION_APP["expires_in"]
        login.reset_mock()
    inicio = Barrier(5)
    login_iniciado = Event()
    liberar_login = Event()

    def autenticar(*args):
        login_iniciado.set()
        assert liberar_login.wait(timeout=5)
        return httpx.Response(200, json={**SESION_APP, "access_token": "token-compartido"})

    def obtener():
        inicio.wait(timeout=5)
        return cloud_client.obtener_token_aplicacion()

    login.side_effect = autenticar
    with ThreadPoolExecutor(max_workers=4) as ejecutor:
        pendientes = [ejecutor.submit(obtener) for _ in range(4)]
        try:
            inicio.wait(timeout=5)
            assert login_iniciado.wait(timeout=5)
        finally:
            liberar_login.set()
        assert [pendiente.result(timeout=5) for pendiente in pendientes] == ["token-compartido"] * 4
    login.assert_called_once()


@pytest.mark.parametrize("fallo", [httpx.ReadTimeout("secreto"), httpx.Response(401),
    httpx.Response(200, json={**SESION_APP, "expires_in": True})])
def test_renovacion_fallida_no_entrega_vencido_ni_cachea_fallo(sesion_simulada, fallo):
    reloj, login = sesion_simulada
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    reloj[0] += SESION_APP["expires_in"]
    login.side_effect = [fallo, httpx.Response(200, json={**SESION_APP, "access_token": "recuperado"})]
    with pytest.raises(cloud_client.AutenticacionAplicacionError):
        cloud_client.obtener_token_aplicacion()
    assert cloud_client.obtener_token_aplicacion() == "recuperado"
    assert cloud_client.obtener_token_aplicacion() == "recuperado"
    assert login.call_count == 3


@pytest.mark.parametrize("variable", ["CLOUD_API_URL", "CLOUD_APP_USUARIO", "CLOUD_APP_PASSWORD"])
def test_cambio_configuracion_no_reutiliza_token_anterior(sesion_simulada, monkeypatch, variable):
    _, login = sesion_simulada
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    monkeypatch.setenv(variable, "https://otro.example.test" if variable == "CLOUD_API_URL" else "otra-credencial")
    login.return_value = httpx.Response(200, json={**SESION_APP, "access_token": "otra-configuracion"})
    assert cloud_client.obtener_token_aplicacion() == "otra-configuracion"
    assert login.call_count == 2


@pytest.mark.parametrize("variable", ["CLOUD_APP_USUARIO", "CLOUD_APP_PASSWORD"])
def test_credenciales_faltantes_rechazan_incluso_con_cache(sesion_simulada, monkeypatch, variable):
    _, login = sesion_simulada
    assert cloud_client.obtener_token_aplicacion() == TOKEN_APP
    monkeypatch.delenv(variable)
    with pytest.raises(cloud_client.AutenticacionAplicacionError):
        cloud_client.obtener_token_aplicacion()
    login.assert_called_once()
