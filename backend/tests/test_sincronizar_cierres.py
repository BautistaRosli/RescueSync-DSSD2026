"""Reconcilia cierres confirmados sin ejecutar operaciones externas."""

from unittest.mock import AsyncMock

import pytest

from app.integrations.bonita.client import BonitaClientError, bonita_client
from app.models import Emergencia, EstadoEmergencia
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_concurrencia import sesiones_pg
from test_permisos_api import cabecera, entorno, estado


RUTA = "/api/v1/emergencias/sincronizar-cierres"


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
