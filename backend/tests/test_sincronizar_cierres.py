"""Reconcilia cierres confirmados sin ejecutar operaciones externas."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.integrations import cloud_client
from app.integrations.bonita.client import BonitaClientError, bonita_client
from app.models import Emergencia, EstadoEmergencia, RegistroRecursos
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_concurrencia import sesiones_pg
from test_permisos_api import cabecera, entorno, estado


RUTA = "/api/v1/emergencias/sincronizar-cierres"

RECIBO = {"emergencia_id": 2, "total_liberado": 6, "compromisos_liberados": [
    {"ong_id": 101, "item_id": 900, "cantidad": 6, "estado_anterior": "BLOQUEADO", "lote_id": None},
]}


@pytest.fixture(autouse=True)
def no_liberar_sin_reserva(monkeypatch):
    liberar = Mock(side_effect=AssertionError("No debe liberar recursos"))
    monkeypatch.setattr(cloud_client, "liberar_emergencia", liberar, raising=False)
    return liberar


def preparar_registro(sesiones, emergencia_id=2, caso_id="42", estado_registro="CONFIRMADO"):
    with sesiones() as db:
        db.add(RegistroRecursos(emergencia_id=emergencia_id, caso_id=caso_id,
            seleccion_json="[]", solicitud_json="{}", estado=estado_registro))
        db.commit()


@pytest.fixture
def liberacion(entorno, monkeypatch, no_liberar_sin_reserva):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    preparar_registro(sesiones)
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(return_value={"42"}))
    token = Mock(return_value="token-aplicacion")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", token)
    no_liberar_sin_reserva.side_effect = None
    no_liberar_sin_reserva.return_value = httpx.Response(200, json=RECIBO)
    return cliente, sesiones, no_liberar_sin_reserva, token


def preparar_emergencia(sesiones):
    with sesiones() as db:
        emergencia = db.get(Emergencia, 2)
        emergencia.estado = EstadoEmergencia.EN_PROCESO
        emergencia.bonita_case_id = "42"
        db.commit()


def test_sincronizar_mueve_a_resueltas_y_es_idempotente(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    consulta = AsyncMock(return_value={"42"})
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consulta, raising=False)

    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": [2]}
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": []}
    consulta.assert_awaited_once_with({"42"})
    for estado_actual, esperados in ((EstadoEmergencia.EN_PROCESO, []), (EstadoEmergencia.RESUELTA, [2])):
        respuesta = cliente.get("/api/v1/emergencias/bandeja", params={"publicada": True, "estado": estado_actual}, headers=cabecera(COORDINADOR))
        assert respuesta.status_code == 200, respuesta.text
        assert [fila["id"] for fila in respuesta.json()["items"]] == esperados
        assert respuesta.json()["total"] == len(esperados)


@pytest.mark.parametrize("rol", [OPERADOR, ONG, AUDITOR, None])
def test_sincronizar_restringido_a_coordinador(entorno, monkeypatch, rol):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    consulta = AsyncMock(return_value={"42"})
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consulta, raising=False)
    anterior = estado(sesiones)
    respuesta = cliente.post(RUTA, headers=cabecera(rol) if rol else {})
    assert respuesta.status_code == (403 if rol else 401)
    assert estado(sesiones) == anterior
    consulta.assert_not_awaited()


def test_sincronizar_no_cambia_nada_ante_error(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(side_effect=BonitaClientError("sin conexión")), raising=False)
    anterior = estado(sesiones)
    respuesta = cliente.post(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("cambio", [{"bonita_case_id": "43"}, {"estado": EstadoEmergencia.ESPERA_OFERTAS}, {"publicada": False}])
def test_sincronizar_revalida_caso_estado_y_publicacion_despues_del_http(entorno, monkeypatch, cambio):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    preparar_registro(sesiones)

    async def consultar(casos):
        assert casos == {"42"}
        with sesiones() as db:
            emergencia = db.get(Emergencia, 2)
            for campo, valor in cambio.items():
                setattr(emergencia, campo, valor)
            db.commit()
        return {"42"}

    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consultar, raising=False)
    respuesta = cliente.post(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"emergencias_resueltas": []}
    with sesiones() as db:
        emergencia = db.get(Emergencia, 2)
        assert emergencia.estado != EstadoEmergencia.RESUELTA
        for campo, valor in cambio.items():
            assert getattr(emergencia, campo) == valor


def test_solo_consulta_publicadas_en_proceso_con_caso_valido_y_get_no_muta(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.bonita_case_id = "99"
        emergencia.estado = EstadoEmergencia.EN_PROCESO
        db.commit()
    consulta = AsyncMock(return_value=set())
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consulta, raising=False)
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/bandeja?publicada=true&estado=en_proceso", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200
    assert estado(sesiones) == anterior
    consulta.assert_not_awaited()
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).status_code == 200
    consulta.assert_awaited_once_with({"42"})


def test_sincronizar_libera_transaccion_antes_de_consultar_bonita(entorno, monkeypatch):
    from app.api.routes.emergencias_api import servicio_emergencias

    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    original = servicio_emergencias._repository.listar_candidatos_cierre
    capturadas = []

    def listar(db):
        capturadas.append(db)
        return original(db)

    async def consultar(casos):
        assert casos == {"42"}
        assert not capturadas[0].in_transaction()
        return {"42"}

    monkeypatch.setattr(servicio_emergencias._repository, "listar_candidatos_cierre", listar)
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consultar)
    respuesta = cliente.post(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"emergencias_resueltas": [2]}


def test_postgresql_dos_sincronizaciones_resuelven_una_sola_vez(sesiones_pg, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.services.emergencias_service import EmergenciaService

    encuentro = Barrier(2)
    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.publicada = True
        emergencia.estado = EstadoEmergencia.EN_PROCESO
        emergencia.bonita_case_id = "42"
        db.commit()

    async def consultar(casos):
        assert casos == {"42"}
        encuentro.wait(timeout=5)
        return {"42"}

    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consultar)

    def sincronizar():
        with sesiones_pg() as db:
            return asyncio.run(EmergenciaService().sincronizar_cierres(db)).emergencias_resueltas

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(lambda _: sincronizar(), range(2)))
    assert sorted(resultados) == [[], [1]]
    with sesiones_pg() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.RESUELTA


def test_libera_reserva_confirmada_antes_de_resolver_y_no_repite(liberacion):
    cliente, sesiones, liberar, token = liberacion

    def confirmar(emergencia_id, token_app):
        with sesiones() as db:
            assert db.get(Emergencia, emergencia_id).estado == EstadoEmergencia.EN_PROCESO
        return httpx.Response(200, json=RECIBO)

    liberar.side_effect = confirmar
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": [2]}
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": []}
    liberar.assert_called_once_with(2, "token-aplicacion")
    token.assert_called_once_with()
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.RESUELTA


@pytest.mark.parametrize("fallo", [
    httpx.Response(401), httpx.Response(500), httpx.Response(302), httpx.Response(204),
    httpx.Response(200, content="no-json"), httpx.Response(200, json=[]),
    *[httpx.Response(200, json=datos) for datos in (
        {}, {**RECIBO, "emergencia_id": 99}, {**RECIBO, "total_liberado": True},
        {**RECIBO, "total_liberado": -1}, {**RECIBO, "total_liberado": 5},
        {**RECIBO, "compromisos_liberados": {}},
        {**RECIBO, "compromisos_liberados": [{"cantidad": 6}]},
    )],
    httpx.ReadTimeout("sin respuesta"), httpx.InvalidURL("sin URL"),
])
def test_fallo_liberacion_conserva_en_proceso_y_reintento_cero_resuelve(liberacion, fallo):
    cliente, sesiones, liberar, _ = liberacion
    liberar.side_effect = [fallo, httpx.Response(200, json={"emergencia_id": 2,
        "total_liberado": 0, "compromisos_liberados": []})]
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).status_code == 503
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    respuesta = cliente.post(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"emergencias_resueltas": [2]}
    assert liberar.call_count == 2
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.RESUELTA


def test_fallo_token_no_libera_ni_resuelve(liberacion):
    cliente, sesiones, liberar, token = liberacion
    token.side_effect = cloud_client.AutenticacionAplicacionError()
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).status_code == 503
    liberar.assert_not_called()
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


@pytest.mark.parametrize("estado_registro,caso", [("ENVIADO", "42"), ("ENVIADO", "43"), ("CONFIRMADO", "43")])
def test_reserva_incierta_o_de_otro_caso_no_libera_ni_resuelve(entorno, monkeypatch, estado_registro, caso):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    preparar_registro(sesiones, caso_id=caso, estado_registro=estado_registro)
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(return_value={"42"}))
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).status_code == 503
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


def test_reserva_rechazada_conserva_cierre_historico_sin_liberar(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_emergencia(sesiones)
    preparar_registro(sesiones, estado_registro="RECHAZADO")
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(return_value={"42"}))
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": [2]}


def test_caso_activo_o_abortado_no_libera(liberacion, monkeypatch):
    cliente, sesiones, liberar, _ = liberacion
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(return_value=set()))
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).json() == {"emergencias_resueltas": []}
    liberar.assert_not_called()
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


def test_fallo_de_una_liberacion_no_revierte_ni_impide_otros_cierres(liberacion, monkeypatch):
    cliente, sesiones, liberar, _ = liberacion
    with sesiones() as db:
        for emergencia_id in (1, 3):
            emergencia = db.get(Emergencia, emergencia_id)
            if emergencia is None:
                emergencia = Emergencia(id=emergencia_id, nivel_gravedad="media", zona_afectada="Zona",
                    descripcion_inicial="Otra emergencia")
                db.add(emergencia)
            emergencia.publicada = True
            emergencia.estado = EstadoEmergencia.EN_PROCESO
            emergencia.bonita_case_id = str(40 + emergencia_id)
        db.commit()
    preparar_registro(sesiones, emergencia_id=1, caso_id="41")
    preparar_registro(sesiones, emergencia_id=3, caso_id="43")
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", AsyncMock(return_value={"41", "42", "43"}))
    liberar.side_effect = [httpx.Response(200, json={**RECIBO, "emergencia_id": 1}),
        httpx.ReadTimeout("sin respuesta"), httpx.Response(200, json={**RECIBO, "emergencia_id": 3})]
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR)).status_code == 503
    assert [llamada.args[0] for llamada in liberar.call_args_list] == [1, 2, 3]
    with sesiones() as db:
        assert [db.get(Emergencia, i).estado for i in (1, 2, 3)] == [
            EstadoEmergencia.RESUELTA, EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA]


def test_postgresql_sincronizaciones_con_reserva_liberan_una_sola_vez(sesiones_pg, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.emergencias_service import EmergenciaService

    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.publicada = True
        emergencia.estado = EstadoEmergencia.EN_PROCESO
        emergencia.bonita_case_id = "42"
        db.commit()
    preparar_registro(sesiones_pg, emergencia_id=1)
    encuentro = Barrier(2)

    async def consultar(casos):
        encuentro.wait(timeout=5)
        return {"42"}

    liberar = Mock(return_value=httpx.Response(200, json={**RECIBO, "emergencia_id": 1}))
    monkeypatch.setattr(bonita_client, "obtener_casos_completados", consultar)
    monkeypatch.setattr(cloud_client, "liberar_emergencia", liberar)
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-aplicacion"))

    def sincronizar(_):
        with sesiones_pg() as db:
            return asyncio.run(EmergenciaService().sincronizar_cierres(db)).emergencias_resueltas

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(sincronizar, range(2)))
    assert sorted(resultados) == [[], [1]]
    liberar.assert_called_once_with(1, "token-aplicacion")
    with sesiones_pg() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.RESUELTA
