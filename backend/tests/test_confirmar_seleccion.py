"""Confirmación HTTP con SQLite y transporte Bonita exclusivamente simulado."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.integrations.bonita.client import bonita_client
from app.models import Emergencia, OfertaAyuda, OfertaItem
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno, estado
from test_concurrencia import sesiones_pg


RUTA = "/api/v1/emergencias/2/confirmar-seleccion"
PARES = [{"oferta_id": 1, "lote_id": 2}, {"oferta_id": 2, "lote_id": 2}]


@pytest.fixture
def seleccion(entorno, monkeypatch):
    cliente, sesiones, dobles = entorno
    with sesiones() as db:
        db.get(Emergencia, 2).bonita_case_id = "42"
        for oferta_id in (1, 2):
            db.get(OfertaAyuda, oferta_id).adjudicada_en = datetime.now(timezone.utc)
        db.add(OfertaItem(oferta_id=2, lote_necesidad_id=2, cantidad_ofrecida=3))
        db.commit()
    motor = {"seleccion": [], "evaluacion": {"emergencia_id": 2, "resultados": [
        {**par, "cantidad_verificada": 3} for par in PARES]},
        "tarea": {"id": "99", "caseId": "42", "name": "Seleccionar oferta",
                  "actorId": "7", "assigned_id": "0"},
        "ejecuciones": [], "asignaciones": [], "archivado": False,
        "caido": False, "respuesta_perdida": False, "concurrente": False,
        "respuesta_invalida": False}
    barrera = Barrier(2, timeout=10)
    bloqueo = Lock()
    lecturas_iniciales = 0

    def transportar(request):
        nonlocal lecturas_iniciales
        ruta = request.url.path
        if motor["caido"]:
            raise httpx.ConnectError("Caída simulada", request=request)
        if ruta == "/loginservice":
            return httpx.Response(204)
        if "/caseVariable/42/" in ruta or "/archivedCaseVariable/42/" in ruta:
            if motor["respuesta_invalida"]:
                return httpx.Response(200, json=[])
            if "/caseVariable/" in ruta and motor["archivado"]:
                return httpx.Response(404)
            variable = ruta.rsplit("/", 1)[1]
            valor = motor["seleccion"] if variable == "seleccionOfertasJson" else motor["evaluacion"]
            if variable == "seleccionOfertasJson" and motor["concurrente"]:
                with bloqueo:
                    lecturas_iniciales += 1
                    esperar = lecturas_iniciales <= 2
                if esperar:
                    valor = []
                    barrera.wait()
            return httpx.Response(200, json={"value": json.dumps(valor)})
        if ruta == "/API/bpm/userTask":
            assert request.url.params.get_list("f") == ["caseId=42", "name=Seleccionar oferta"]
            return httpx.Response(200, json=[motor["tarea"]] if motor["tarea"] else [])
        if ruta == "/API/bpm/actorMember":
            assert "actor_id=7" in request.url.params.get_list("f")
            return httpx.Response(200, json=[{"id": "400", "actor_id": "7", "user_id": "12"}])
        if ruta == "/API/bpm/userTask/99" and request.method == "PUT":
            if motor["tarea"] is None:
                return httpx.Response(409)
            motor["asignaciones"].append(json.loads(request.content))
            motor["tarea"]["assigned_id"] = "12"
            return httpx.Response(204)
        if ruta == "/API/bpm/userTask/99/execution":
            cuerpo = json.loads(request.content)
            with bloqueo:
                if motor["tarea"] is None:
                    return httpx.Response(409)
                motor["ejecuciones"].append(cuerpo)
                motor["seleccion"] = cuerpo["seleccionInput"]
                motor["tarea"] = None
            if motor["respuesta_perdida"]:
                motor["archivado"] = True
                raise httpx.ReadTimeout("Respuesta perdida", request=request)
            return httpx.Response(204)
        raise AssertionError(f"Petición inesperada: {request.method} {ruta}")

    async def crear_cliente():
        return httpx.AsyncClient(base_url="http://bonita.test", transport=httpx.MockTransport(transportar))

    monkeypatch.setattr(bonita_client, "_client", crear_cliente)
    return cliente, sesiones, motor, dobles


def confirmar(seleccion, rol=COORDINADOR):
    return seleccion[0].post(RUTA, headers=cabecera(rol))


def test_confirma_ofertas_completas_y_reintento_sin_correo(seleccion):
    _, sesiones, motor, dobles = seleccion
    anterior = estado(sesiones)
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"emergencia_id": 2, "cantidad_pares": 2, "ya_confirmada": False}
    assert motor["ejecuciones"] == [{"seleccionInput": PARES}]
    assert motor["asignaciones"] == [{"assigned_id": "12"}]
    motor["seleccion"].reverse()
    motor["archivado"] = True
    reintento = confirmar(seleccion)
    assert reintento.status_code == 200 and reintento.json()["ya_confirmada"] is True
    assert len(motor["ejecuciones"]) == 1
    assert estado(sesiones) == anterior
    dobles[1].assert_not_called()


@pytest.mark.parametrize("cambio", ["vacia", "sin_caso", "sin_tarea", "cantidad_cero",
                                    "otra_emergencia", "par_ausente", "asignada", "otro_caso"])
def test_conflictos_no_ejecutan_ni_modifican(seleccion, cambio):
    _, sesiones, motor, _ = seleccion
    with sesiones() as db:
        if cambio == "vacia":
            for oferta in db.query(OfertaAyuda):
                oferta.adjudicada_en = None
        if cambio == "sin_caso":
            db.get(Emergencia, 2).bonita_case_id = None
        db.commit()
    if cambio == "sin_tarea":
        motor["tarea"] = None
    elif cambio == "cantidad_cero":
        motor["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    elif cambio == "otra_emergencia":
        motor["evaluacion"]["emergencia_id"] = 1
    elif cambio == "par_ausente":
        motor["evaluacion"]["resultados"].pop()
    elif cambio == "asignada":
        motor["tarea"]["assigned_id"] = "88"
    elif cambio == "otro_caso":
        motor["tarea"]["caseId"] = "51"
    anterior = estado(sesiones)
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 409, respuesta.text
    assert motor["ejecuciones"] == [] and motor["asignaciones"] == []
    assert estado(sesiones) == anterior


def test_respuesta_perdida_reconoce_ejecucion_archivada(seleccion):
    motor = seleccion[2]
    motor["respuesta_perdida"] = True
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200 and respuesta.json()["ya_confirmada"] is True
    assert len(motor["ejecuciones"]) == 1


def test_caida_no_se_confunde_con_tarea_ausente(seleccion):
    seleccion[2]["caido"] = True
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 503, respuesta.text


def test_seleccion_distinta_no_reabre_tarea(seleccion):
    motor = seleccion[2]
    motor["seleccion"] = PARES[:1]
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 409 and motor["ejecuciones"] == []


def test_no_incluye_ofertas_sin_adjudicar_ni_de_otra_emergencia(seleccion):
    _, sesiones, motor, _ = seleccion
    with sesiones() as db:
        db.get(OfertaAyuda, 2).adjudicada_en = None
        db.add(OfertaAyuda(id=3, emergencia_id=1, organizacion_id=1,
                          adjudicada_en=datetime.now(timezone.utc),
                          items=[OfertaItem(lote_necesidad_id=1, cantidad_ofrecida=2)]))
        db.commit()
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200 and respuesta.json()["cantidad_pares"] == 1
    assert motor["ejecuciones"] == [{"seleccionInput": PARES[:1]}]


def test_adjudicacion_posterior_no_cambia_seleccion_confirmada(seleccion):
    _, sesiones, motor, _ = seleccion
    assert confirmar(seleccion).status_code == 200
    with sesiones() as db:
        db.add(OfertaAyuda(id=3, emergencia_id=2, organizacion_id=1,
                          adjudicada_en=datetime.now(timezone.utc),
                          items=[OfertaItem(lote_necesidad_id=2, cantidad_ofrecida=2)]))
        db.commit()
    assert confirmar(seleccion).status_code == 409
    assert motor["seleccion"] == PARES and len(motor["ejecuciones"]) == 1


def test_asignacion_propia_se_conserva(seleccion):
    motor = seleccion[2]
    motor["tarea"]["assigned_id"] = "12"
    assert confirmar(seleccion).status_code == 200
    assert motor["asignaciones"] == []


def test_confirmaciones_simultaneas_reconocen_un_solo_avance_del_motor(seleccion, monkeypatch):
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    # SQLite StaticPool comparte una conexión: la concurrencia del motor se
    # prueba con lecturas locales inmutables para no usarla desde dos hilos.
    emergencia = SimpleNamespace(bonita_case_id="42")
    ofertas = [SimpleNamespace(id=numero, adjudicada_en=True, items=[SimpleNamespace(
        lote_necesidad_id=2, cantidad_ofrecida=3, lote_necesidad=SimpleNamespace(emergencia_id=2))])
        for numero in (1, 2)]
    monkeypatch.setattr("app.services.seleccion_ofertas_service.EmergenciaRepository.obtener_por_id",
                        lambda *args, **kwargs: emergencia)
    monkeypatch.setattr("app.services.seleccion_ofertas_service.OfertaRepository.listar_de_emergencia",
                        lambda *args: ofertas)
    motor = seleccion[2]
    motor["concurrente"] = True
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        respuestas = list(ejecutor.map(
            lambda _: asyncio.run(SeleccionOfertasService().confirmar(Mock(), 2)), range(2)))
    assert [respuesta.cantidad_pares for respuesta in respuestas] == [2, 2]
    assert len(motor["ejecuciones"]) == 1


def test_identificador_caso_no_numerico_es_conflicto(seleccion):
    with seleccion[1]() as db:
        db.get(Emergencia, 2).bonita_case_id = "caso-invalido"
        db.commit()
    assert confirmar(seleccion).status_code == 409


def test_respuesta_bonita_malformada_es_indisponibilidad(seleccion):
    seleccion[2]["respuesta_invalida"] = True
    assert confirmar(seleccion).status_code == 503


def test_confirmaciones_postgresql_se_serializan(sesiones_pg, monkeypatch):
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    with sesiones_pg() as db:
        db.get(Emergencia, 1).bonita_case_id = "42"
        oferta = db.get(OfertaAyuda, 1)
        oferta.adjudicada_en = datetime.now(timezone.utc)
        oferta.items = [OfertaItem(lote_necesidad_id=1, cantidad_ofrecida=3)]
        db.commit()
    entro_primera = Event()
    liberar_primera = Event()
    segunda_iniciada = Event()
    guardada = []

    async def variable(caso_id, nombre):
        assert caso_id == 42
        if nombre == "seleccionOfertasJson":
            if not guardada:
                entro_primera.set()
                assert await asyncio.to_thread(liberar_primera.wait, 5)
            return json.dumps(guardada)
        return json.dumps({"emergencia_id": 1, "resultados": [
            {"oferta_id": 1, "lote_id": 1, "cantidad_verificada": 3}]})

    async def ejecutar(tarea_id, contrato):
        guardada.extend(contrato["seleccionInput"])

    monkeypatch.setattr(bonita_client, "obtener_variable_caso", variable)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value={
        "id": "99", "caseId": "42", "name": "Seleccionar oferta", "actorId": "7", "assigned_id": "12"}))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    ejecucion = AsyncMock(side_effect=ejecutar)
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecucion)

    def confirmar_en_sesion(segunda=False):
        with sesiones_pg() as db:
            if segunda:
                segunda_iniciada.set()
            return asyncio.run(SeleccionOfertasService().confirmar(db, 1))

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        primera = ejecutor.submit(confirmar_en_sesion)
        assert entro_primera.wait(5)
        segunda = ejecutor.submit(confirmar_en_sesion, True)
        try:
            assert segunda_iniciada.wait(5)
            with pytest.raises(TimeoutError):
                segunda.result(timeout=0.1)
        finally:
            liberar_primera.set()
        assert primera.result(timeout=10).ya_confirmada is False
        assert segunda.result(timeout=10).ya_confirmada is True
    ejecucion.assert_awaited_once()


@pytest.mark.parametrize("rol,codigo", [(ONG, 403), (OPERADOR, 403), (AUDITOR, 200)])
def test_roles_y_alcance_existentes(seleccion, rol, codigo):
    respuesta = confirmar(seleccion, rol)
    assert respuesta.status_code == codigo, respuesta.text


def test_sin_autenticacion_y_emergencia_inexistente(seleccion):
    cliente = seleccion[0]
    assert cliente.post(RUTA).status_code == 401
    assert cliente.post(RUTA.replace("/2/", "/999/"), headers=cabecera(COORDINADOR)).status_code == 404
