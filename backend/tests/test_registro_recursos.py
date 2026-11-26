"""Registro HTTP con evaluación local e integraciones exclusivamente simuladas."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Barrier, Event
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app
from app.models import (Emergencia, EstadoEmergencia, EvaluacionCloud, LoteNecesidad, LoteRecursoCloud,
                        OfertaAyuda, OfertaItem, RegistroRecursos, Rol, Usuario)
from app.integrations import cloud_client
from app.integrations.bonita.client import bonita_client
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno
from test_concurrencia import sesiones_pg


RUTA = "/api/v1/emergencias/2/registrar-recursos"
ENTRADA = {"caso_id": 42, "seleccion": [{"oferta_id": 1, "lote_id": 2}, {"oferta_id": 2, "lote_id": 2}]}
PEDIDO = {"emergencia_id": 2, "ongs": [
    {"ong_id": 101, "items": [{"item_id": 900, "cantidad": 5}]},
    {"ong_id": 102, "items": [{"item_id": 900, "cantidad": 1}]},
]}
RECIBO = {"emergencia_id": 2, "lote_id": None, "total_bloqueado": 6, "bloqueados": [
    {"ong_id": 101, "item_id": 900, "cantidad": 5, "estado": "BLOQUEADO"},
    {"ong_id": 102, "item_id": 900, "cantidad": 1, "estado": "BLOQUEADO"},
]}


def ronda():
    ofertas = []
    resultados = []
    for oferta_id, cantidades in [(1, [(101, 4, 2), (102, 1, 1)]), (2, [(101, 4, 3)])]:
        ofertas.append({"oferta_id": oferta_id, "lote_id": 2, "ong_responsable_id": 101,
                        "aportes": [{"ong_id": ong, "items": [{"tipo_recurso_id": 900, "cantidad": ofrecida}]}
                                    for ong, ofrecida, _ in cantidades]})
        resultados.append({"oferta_id": oferta_id, "lote_id": 2, "es_consorcio": oferta_id == 1,
                           "nivel_habilitacion": "PARCIAL", "cantidad_ofrecida": sum(c[1] for c in cantidades),
                           "cantidad_verificada": sum(c[2] for c in cantidades), "cobertura_lote_pct": 30,
                           "observaciones": [], "participantes": [
                               {"ong_id": ong, "rol": "PRINCIPAL" if indice == 0 else "APOYO_SECUNDARIO",
                                "habilitada": True, "capacidades_habilitadas": [
                                    {"tipo_recurso_id": 900, "cantidad_ofrecida": ofrecida, "cantidad_verificada": verificada}]}
                               for indice, (ong, ofrecida, verificada) in enumerate(cantidades)]})
    return ({"emergencia_id": 2, "lotes": [{"lote_id": 2, "tipo_recurso_id": 900, "cantidad_requerida": 2}],
             "ofertas": ofertas}, {"emergencia_id": 2, "resultados": resultados})


@pytest.fixture
def registro(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    solicitud, evaluacion = ronda()
    with sesiones() as db:
        db.get(Emergencia, 2).bonita_case_id = "42"
        db.get(Emergencia, 2).estado = EstadoEmergencia.EN_PROCESO
        for oferta in db.query(OfertaAyuda):
            oferta.adjudicada_en = datetime.now(timezone.utc)
        db.add(OfertaItem(oferta_id=2, lote_necesidad_id=2, cantidad_ofrecida=4))
        db.add(LoteRecursoCloud(lote_id=2, tipo_recurso_id=900))
        db.add(EvaluacionCloud(emergencia_id=2, solicitud_id="ronda", caso_id="42",
                               solicitud_json=json.dumps(solicitud), evaluacion_json=json.dumps(evaluacion)))
        db.commit()
    transporte = Mock(return_value=httpx.Response(200, json=RECIBO))
    monkeypatch.setattr(cloud_client, "bloquear_recursos", transporte, raising=False)
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-prueba"))
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", AsyncMock(return_value=json.dumps(ENTRADA["seleccion"])))
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", Mock(side_effect=AssertionError("Sin lectura Bonita")))
    return cliente, sesiones, transporte


def registrar(registro, entrada=None, rol=COORDINADOR):
    return registro[0].post(RUTA, json=entrada or ENTRADA, headers=cabecera(rol))


def test_reserva_verificadas_agrupadas_una_vez_y_repite_204(registro):
    assert registrar(registro).status_code == 204
    assert registrar(registro, {**ENTRADA, "seleccion": list(reversed(ENTRADA["seleccion"]))}).status_code == 204
    registro[2].assert_called_once_with(PEDIDO, "token-prueba")
    with registro[1]() as db:
        guardado = db.get(RegistroRecursos, 2)
        assert guardado.estado == "CONFIRMADO"
        assert json.loads(guardado.respuesta_json) == RECIBO
        db.get(Emergencia, 2).estado = EstadoEmergencia.RESUELTA
        db.commit()
    assert registrar(registro).status_code == 204


def test_auditor_puede_registrar(registro):
    assert registrar(registro, rol=AUDITOR).status_code == 204


def test_sin_autenticacion_no_envia(registro):
    assert registro[0].post(RUTA, json=ENTRADA).status_code == 401
    registro[2].assert_not_called()


def test_fallo_login_no_reserva_y_permite_reintentar(registro, monkeypatch):
    token = Mock(side_effect=[cloud_client.AutenticacionAplicacionError(), "token-prueba"])
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", token)
    assert registrar(registro).status_code == 503
    registro[2].assert_not_called()
    assert registrar(registro).status_code == 204


def test_adjudicacion_individual_sin_seleccion_real_no_reserva(registro, monkeypatch):
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", AsyncMock(return_value="[]"))
    assert registrar(registro).status_code == 409
    registro[2].assert_not_called()
    with registro[1]() as db:
        assert db.get(RegistroRecursos, 2) is None


def test_replay_confirmado_no_depende_de_bonita(registro, monkeypatch):
    assert registrar(registro).status_code == 204
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", AsyncMock(side_effect=httpx.ReadTimeout("caído")))
    assert registrar(registro).status_code == 204
    assert registro[2].call_count == 1


@pytest.mark.parametrize("commit_fallido", [1, 2])
def test_fallo_commit_no_envia_o_no_repite_reserva_incierta(registro, monkeypatch, commit_fallido):
    original = registro[1].class_.commit
    intentos = 0

    def confirmar(db):
        nonlocal intentos
        intentos += 1
        if intentos == commit_fallido:
            raise OperationalError("fallo simulado", None, Exception())
        return original(db)

    monkeypatch.setattr(registro[1].class_, "commit", confirmar)
    assert registrar(registro).status_code == 503
    assert registro[2].call_count == commit_fallido - 1
    with registro[1]() as db:
        guardado = db.get(RegistroRecursos, 2)
        assert guardado is None if commit_fallido == 1 else guardado.estado == "ENVIADO"
    assert registrar(registro).status_code == (204 if commit_fallido == 1 else 409)
    assert registro[2].call_count == 1


def test_reintento_no_puede_cambiar_seleccion(registro):
    registro[2].return_value = httpx.Response(409)
    assert registrar(registro).status_code == 409
    assert registrar(registro, {**ENTRADA, "seleccion": ENTRADA["seleccion"][:1]}).status_code == 409
    assert registro[2].call_count == 1


def test_reintento_seguro_conserva_payload_original(registro):
    registro[2].side_effect = [httpx.Response(409), httpx.Response(200, json=RECIBO)]
    assert registrar(registro).status_code == 409
    with registro[1]() as db:
        db.query(EvaluacionCloud).one().evaluacion_json = "{}"
        db.commit()
    assert registrar(registro).status_code == 204
    assert all(llamada.args[0] == PEDIDO for llamada in registro[2].call_args_list)


def test_mismo_recurso_en_varios_lotes_se_suma_sin_limitar_a_demanda(registro, monkeypatch):
    with registro[1]() as db:
        actual = db.query(EvaluacionCloud).one()
        solicitud, evaluacion = json.loads(actual.solicitud_json), json.loads(actual.evaluacion_json)
        solicitud["lotes"].append({"lote_id": 3, "tipo_recurso_id": 900, "cantidad_requerida": 1})
        solicitud["ofertas"].append({**deepcopy(solicitud["ofertas"][1]), "lote_id": 3})
        evaluacion["resultados"].append({**deepcopy(evaluacion["resultados"][1]), "lote_id": 3})
        actual.solicitud_json, actual.evaluacion_json = json.dumps(solicitud), json.dumps(evaluacion)
        db.add(LoteNecesidad(id=3, emergencia_id=2, tipo="Agua", cantidad=1))
        db.flush()
        db.add(LoteRecursoCloud(lote_id=3, tipo_recurso_id=900))
        db.add(OfertaItem(oferta_id=2, lote_necesidad_id=3, cantidad_ofrecida=4))
        db.commit()
    recibo = deepcopy(RECIBO)
    recibo["total_bloqueado"], recibo["bloqueados"][0]["cantidad"] = 9, 8
    registro[2].return_value = httpx.Response(200, json=recibo)
    entrada = {**ENTRADA, "seleccion": [*ENTRADA["seleccion"], {"oferta_id": 2, "lote_id": 3}]}
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", AsyncMock(return_value=json.dumps(entrada["seleccion"])))
    assert registrar(registro, entrada).status_code == 204
    pedido = deepcopy(PEDIDO)
    pedido["ongs"][0]["items"][0]["cantidad"] = 8
    registro[2].assert_called_once_with(pedido, "token-prueba")


def test_transporte_cloud_envia_contrato_agrupado_y_bearer(monkeypatch):
    enviar = Mock(return_value=httpx.Response(200, json=RECIBO))
    monkeypatch.setattr(httpx, "post", enviar)
    monkeypatch.setenv("CLOUD_API_URL", "http://cloud.test/")
    respuesta = cloud_client.bloquear_recursos(PEDIDO, "token-prueba")
    assert respuesta.status_code == 200
    enviar.assert_called_once_with("http://cloud.test/recursos/bloquear", json=PEDIDO,
                                   headers={"Authorization": "Bearer token-prueba"},
                                   timeout=cloud_client.TIEMPO_LIMITE)


@pytest.mark.parametrize("rol", [ONG, OPERADOR])
def test_rechaza_roles_sin_enviar(registro, rol):
    assert registrar(registro, rol=rol).status_code == 403
    registro[2].assert_not_called()


@pytest.mark.parametrize("cambio", ["caso", "seleccion", "duplicada", "cero", "booleano"])
def test_rechaza_entrada_ajena_o_invalida(registro, cambio):
    entrada = deepcopy(ENTRADA)
    if cambio == "caso":
        entrada["caso_id"] = 43
    elif cambio == "seleccion":
        entrada["seleccion"].pop()
    elif cambio == "duplicada":
        entrada["seleccion"].append(entrada["seleccion"][0])
    elif cambio == "cero":
        entrada["seleccion"][0]["lote_id"] = 0
    else:
        entrada["caso_id"] = True
    assert registrar(registro, entrada).status_code in (409, 422)
    registro[2].assert_not_called()


@pytest.mark.parametrize("cambio", ["provisional", "resuelta", "sin_ronda", "obsoleta", "sin_evaluacion", "sin_tipo",
                                   "ong_ajena", "tipo_ajeno", "exceso", "suma", "cero", "sin_disponibilidad"])
def test_rechaza_seleccion_sin_evidencia_verificada(registro, cambio):
    with registro[1]() as db:
        emergencia = db.get(Emergencia, 2)
        actual = db.query(EvaluacionCloud).one()
        evaluacion = json.loads(actual.evaluacion_json)
        capacidad = evaluacion["resultados"][0]["participantes"][0]["capacidades_habilitadas"][0]
        if cambio == "provisional":
            emergencia.estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        elif cambio == "resuelta":
            emergencia.estado = EstadoEmergencia.RESUELTA
        elif cambio == "sin_ronda":
            db.delete(actual)
        elif cambio == "obsoleta":
            actual.vigente = False
        elif cambio == "sin_evaluacion":
            actual.evaluacion_json = None
        elif cambio == "sin_tipo":
            db.delete(db.get(LoteRecursoCloud, 2))
        elif cambio == "ong_ajena":
            evaluacion["resultados"][0]["participantes"][0]["ong_id"] = 999
        elif cambio == "tipo_ajeno":
            capacidad["tipo_recurso_id"] = 999
        elif cambio == "exceso":
            capacidad["cantidad_verificada"] = 5
        elif cambio == "suma":
            evaluacion["resultados"][0]["cantidad_verificada"] = 4
        elif cambio == "cero":
            evaluacion["resultados"][0]["cantidad_verificada"] = 0
        else:
            evaluacion["resultados"][0]["nivel_habilitacion"] = "SIN_DISPONIBILIDAD"
        if cambio not in ("sin_ronda", "sin_evaluacion"):
            actual.evaluacion_json = json.dumps(evaluacion)
        db.commit()
    assert registrar(registro).status_code == 409
    registro[2].assert_not_called()


@pytest.mark.parametrize("codigo", [401, 403, 404, 409, 422])
def test_rechazo_atomico_permite_reintentar_mismo_pedido(registro, codigo):
    registro[2].side_effect = [httpx.Response(codigo, text="secreto-remoto"), httpx.Response(200, json=RECIBO)]
    respuesta = registrar(registro)
    assert respuesta.status_code != 204
    assert "secreto-remoto" not in respuesta.text
    assert registrar(registro).status_code == 204
    assert registro[2].call_count == 2


@pytest.mark.parametrize("fallo", [httpx.ReadTimeout("secreto-remoto"), httpx.Response(500, text="secreto-remoto"),
                                   httpx.Response(200, json={})])
def test_resultado_incierto_bloquea_reenvio(registro, fallo):
    registro[2].side_effect = fallo if isinstance(fallo, Exception) else None
    if not isinstance(fallo, Exception):
        registro[2].return_value = fallo
    respuesta = registrar(registro)
    assert respuesta.status_code == 503
    assert "secreto-remoto" not in respuesta.text
    assert registrar(registro).status_code == 409
    assert registro[2].call_count == 1


@pytest.mark.parametrize("cambio", ["emergencia", "cantidad", "estado", "duplicado", "faltante", "lote"])
def test_recibo_inexacto_no_confirma_ni_reenvia(registro, cambio):
    recibo = deepcopy(RECIBO)
    if cambio == "emergencia":
        recibo["emergencia_id"] = 1
    elif cambio == "cantidad":
        recibo["bloqueados"][0]["cantidad"] = 4
    elif cambio == "estado":
        recibo["bloqueados"][0]["estado"] = "LIBERADO"
    elif cambio == "duplicado":
        recibo["bloqueados"].append(recibo["bloqueados"][0])
    elif cambio == "faltante":
        recibo["bloqueados"].pop()
    else:
        recibo["lote_id"] = 2
    registro[2].return_value = httpx.Response(200, json=recibo)
    assert registrar(registro).status_code == 503
    assert registrar(registro).status_code == 409
    assert registro[2].call_count == 1


@pytest.mark.parametrize("simultaneos", [False, True])
def test_postgresql_dos_callbacks_despachan_una_vez_sin_lock_durante_http(sesiones_pg, monkeypatch, simultaneos):
    sesiones = sesiones_pg
    solicitud, evaluacion = ronda()
    solicitud["ofertas"] = solicitud["ofertas"][:1]
    evaluacion["resultados"] = evaluacion["resultados"][:1]
    for documento, clave in [(solicitud, "ofertas"), (evaluacion, "resultados")]:
        documento[clave][0].update(oferta_id=2, lote_id=3)
    solicitud["lotes"][0]["lote_id"] = 3
    with sesiones() as db:
        db.add(Rol(id=2, nombre=COORDINADOR))
        db.flush()
        db.add(Usuario(id=2, email="usuario2@example.org", nombre="Nombre", apellido="Apellido",
                       password_hash="sin-login", rol_id=2))
        db.add(Emergencia(id=2, zona_afectada="Zona", descripcion_inicial="Prueba", publicada=True,
                          estado=EstadoEmergencia.EN_PROCESO, bonita_case_id="42"))
        db.flush()
        db.add(LoteNecesidad(id=3, emergencia_id=2, tipo="Agua", cantidad=2))
        db.add(OfertaAyuda(id=2, emergencia_id=2, organizacion_id=1, adjudicada_en=datetime.now(timezone.utc)))
        db.flush()
        db.add(LoteRecursoCloud(lote_id=3, tipo_recurso_id=900))
        db.add(OfertaItem(oferta_id=2, lote_necesidad_id=3, cantidad_ofrecida=5))
        db.add(EvaluacionCloud(emergencia_id=2, solicitud_id="ronda-pg", caso_id="42",
                               solicitud_json=json.dumps(solicitud), evaluacion_json=json.dumps(evaluacion)))
        db.commit()

    def obtener_db():
        with sesiones() as db:
            yield db

    entro_http, liberar = Event(), Event()

    def enviar(pedido, token):
        assert pedido == {"emergencia_id": 2, "ongs": [
            {"ong_id": 101, "items": [{"item_id": 900, "cantidad": 2}]},
            {"ong_id": 102, "items": [{"item_id": 900, "cantidad": 1}]},
        ]}
        with sesiones() as db:
            assert db.get(RegistroRecursos, 2).estado == "ENVIADO"
            # Durante la carrera inicial, el segundo callback puede estar
            # tomando legítimamente su propio lock para observar ENVIADO.
            if not simultaneos:
                db.query(Emergencia).filter_by(id=2).with_for_update(nowait=True).one()
        entro_http.set()
        assert liberar.wait(10)
        return httpx.Response(200, json={"emergencia_id": 2, "total_bloqueado": 3, "bloqueados": [
            {"ong_id": 101, "item_id": 900, "cantidad": 2, "estado": "BLOQUEADO"},
            {"ong_id": 102, "item_id": 900, "cantidad": 1, "estado": "BLOQUEADO"},
        ]})

    transporte = Mock(side_effect=enviar)
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-prueba"))
    monkeypatch.setattr(cloud_client, "bloquear_recursos", transporte)
    app.dependency_overrides[get_db] = obtener_db
    entrada = {"caso_id": 42, "seleccion": [{"oferta_id": 2, "lote_id": 3}]}
    barrera = Barrier(2, timeout=10)

    async def leer_seleccion(*_):
        if simultaneos:
            barrera.wait()
        return json.dumps(entrada["seleccion"])

    monkeypatch.setattr(bonita_client, "obtener_variable_caso", leer_seleccion)
    # Sin lifespan: no debe tocar el engine de la aplicación.
    cliente = TestClient(app)
    try:
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            primera = ejecutor.submit(cliente.post, RUTA, json=entrada, headers=cabecera(COORDINADOR))
            try:
                if not simultaneos:
                    assert entro_http.wait(10)
                segunda = ejecutor.submit(cliente.post, RUTA, json=entrada, headers=cabecera(COORDINADOR))
                assert entro_http.wait(10)
                completadas, _ = wait([primera, segunda], timeout=5, return_when=FIRST_COMPLETED)
                assert len(completadas) == 1
                assert next(iter(completadas)).result().status_code == 409
            finally:
                liberar.set()
            assert sorted([primera.result(timeout=10).status_code, segunda.result(timeout=10).status_code]) == [204, 409]
        assert cliente.post(RUTA, json=entrada, headers=cabecera(COORDINADOR)).status_code == 204
        assert transporte.call_count == 1
    finally:
        liberar.set()
        cliente.close()
        app.dependency_overrides.clear()
