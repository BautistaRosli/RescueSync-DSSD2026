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
from app.models import Emergencia, EstadoEmergencia, OfertaAyuda, OfertaItem
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
        "respuesta_invalida": False, "evaluando": False}
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
        if ruta == "/API/bpm/userTask" and request.url.params.get_list("f") == ["caseId=42", "name=Evaluar proyecto"]:
            return httpx.Response(200, json=[{"id": "98", "caseId": "42", "name": "Evaluar proyecto",
                                              "state": "ready"}] if motor["evaluando"] else [])
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


def confirmar(seleccion, rol=OPERADOR):
    return seleccion[0].post(RUTA, headers=cabecera(rol))


def comprobar_avisos_pendientes(seleccion, cantidad):
    from app.models import AvisoAdjudicacion

    seleccion[3][1].assert_not_called()
    with seleccion[1]() as db:
        assert db.query(AvisoAdjudicacion).count() == cantidad
        assert all(aviso.enviada_en is None for aviso in db.query(AvisoAdjudicacion))


def estado_sin_intencion(sesiones):
    from app.database import Base

    with sesiones() as db:
        return [list(db.execute(tabla.select())) for tabla in Base.metadata.sorted_tables
                if tabla.name != "confirmaciones_seleccion"]


def preparar_marcas(seleccion):
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        for oferta in db.query(OfertaAyuda):
            oferta.adjudicada_en = None
        db.commit()


def adjudicar(seleccion, oferta_id=1, para_seleccion=False, rol=OPERADOR):
    return seleccion[0].post(
        f"/api/v1/ofertas/{oferta_id}/adjudicar",
        params={"para_seleccion": para_seleccion}, headers=cabecera(rol))


def test_diez_ofrecidas_cero_verificadas_no_marca_ni_notifica(seleccion):
    preparar_marcas(seleccion)
    with seleccion[1]() as db:
        db.get(OfertaAyuda, 1).items[0].cantidad_ofrecida = 10
        db.commit()
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    anterior = estado(seleccion[1])
    respuesta = adjudicar(seleccion, 1, True)
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["detail"] == "La oferta no fue validada por el Sistema Nacional"
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


def test_cinco_verificadas_tras_continuar_parcial_selecciona_y_confirma(seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["evaluacion"]["decision"] = "CONTINUAR_PARCIAL"
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 5
    respuesta = adjudicar(seleccion, 1, True)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"oferta_id": 1, "mensaje": "Seleccionada para confirmar"}
    seleccion[3][1].assert_not_called()
    listado = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    oferta = listado.json()[0]
    assert oferta["estado_seleccion"] == "seleccionada_para_confirmar"
    assert oferta["items"][0]["cantidad_verificada"] == 5
    assert oferta["puede_seleccionar"] is False
    assert confirmar(seleccion).status_code == 200
    assert confirmar(seleccion).json()["ya_confirmada"] is True
    comprobar_avisos_pendientes(seleccion, 1)
    listado = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert listado.json()[0]["estado_seleccion"] == "adjudicada"


@pytest.mark.parametrize("cambio", ["sin_tarea", "sin_lista", "otro_caso", "otra_emergencia", "par_ausente"])
def test_nueva_marca_exige_fase_y_todos_los_pares_verificados(seleccion, cambio):
    preparar_marcas(seleccion)
    if cambio == "sin_tarea":
        seleccion[2]["tarea"] = None
    elif cambio == "sin_lista":
        seleccion[2]["tarea"]["state"] = "initializing"
    elif cambio == "otro_caso":
        seleccion[2]["tarea"]["caseId"] = "51"
    elif cambio == "otra_emergencia":
        seleccion[2]["evaluacion"]["emergencia_id"] = 1
    else:
        seleccion[2]["evaluacion"]["resultados"].pop(0)
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1, True).status_code == 409
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("situacion", ["pendiente", "cero", "sin_tarea", "sin_conexion"])
def test_listado_distingue_pendiente_de_cero_y_bloquea(seleccion, situacion, monkeypatch):
    preparar_marcas(seleccion)
    if situacion == "pendiente":
        seleccion[2]["evaluacion"] = None
    elif situacion == "cero":
        seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    elif situacion == "sin_tarea":
        seleccion[2]["tarea"] = None
    else:
        seleccion[2]["caido"] = True
    leer = AsyncMock(wraps=bonita_client.obtener_variable_caso)
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", leer)
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    oferta = respuesta.json()[0]
    esperado = 0 if situacion == "cero" else (3 if situacion == "sin_tarea" else None)
    assert oferta["items"][0]["cantidad_verificada"] == esperado
    assert oferta["puede_seleccionar"] is False
    assert oferta["estado_seleccion"] == "sin_seleccionar"
    leer.assert_awaited_once_with(42, "evaluacionJson")


def test_listado_ong_conserva_alcance_y_no_consulta_bonita(seleccion, monkeypatch):
    leer = AsyncMock(side_effect=AssertionError("La ONG no necesita consultar Bonita"))
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", leer)
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(ONG))
    assert respuesta.status_code == 200
    assert [oferta["id"] for oferta in respuesta.json()] == [1]
    assert "puede_seleccionar" not in respuesta.json()[0]
    assert "cantidad_verificada" not in respuesta.json()[0]["items"][0]
    leer.assert_not_called()


@pytest.mark.parametrize("etapa", [EstadoEmergencia.ESPERA_LOTES, EstadoEmergencia.ESPERA_OFERTAS])
def test_listado_no_expone_evaluacion_anterior_durante_nueva_convocatoria(seleccion, monkeypatch, etapa):
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = etapa
        db.commit()
    leer = AsyncMock(side_effect=AssertionError("La evaluación anterior no está vigente"))
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", leer)
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200
    assert all(item["cantidad_verificada"] is None for oferta in respuesta.json() for item in oferta["items"])
    assert all(oferta["puede_seleccionar"] is False for oferta in respuesta.json())
    leer.assert_not_called()


def test_marca_previa_invalida_se_revalida_sin_modificar_registro(seleccion):
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1, True).status_code == 409
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


def test_listado_vacio_no_consulta_bonita(seleccion, monkeypatch):
    leer = AsyncMock(side_effect=AssertionError("Una lista vacía no necesita consultar Bonita"))
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", leer)
    with seleccion[1]() as db:
        db.get(Emergencia, 1).bonita_case_id = "41"
        db.get(Emergencia, 1).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        db.commit()
    respuesta = seleccion[0].get("/api/v1/emergencias/1/ofertas", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200 and respuesta.json() == []
    leer.assert_not_called()


def test_listado_distingue_pendiente_cero_y_fase_sin_consultas_por_oferta(seleccion, monkeypatch):
    preparar_marcas(seleccion)
    obtener = AsyncMock(wraps=bonita_client.obtener_variable_caso)
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", obtener)
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    seleccion[2]["evaluacion"]["resultados"].pop()
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    assert [o["items"][0]["cantidad_verificada"] for o in respuesta.json()] == [0, None]
    assert all(o["puede_seleccionar"] is False for o in respuesta.json())
    obtener.assert_awaited_once_with(42, "evaluacionJson")
    obtener.reset_mock()
    seleccion[2]["evaluacion"]["resultados"] = [{**par, "cantidad_verificada": 5} for par in PARES]
    seleccion[2]["tarea"] = None
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert all(o["puede_seleccionar"] is False for o in respuesta.json())
    obtener.reset_mock()
    respuesta = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(ONG))
    assert [o["id"] for o in respuesta.json()] == [1]
    assert "puede_seleccionar" not in respuesta.json()[0]
    obtener.assert_not_awaited()


def test_marcas_multiples_son_idempotentes_y_confirmacion_avanza_estado(seleccion):
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1, True).status_code == 200
    assert estado(seleccion[1]) == anterior
    assert adjudicar(seleccion, 2, True).status_code == 200
    seleccion[3][1].assert_not_called()
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
    assert confirmar(seleccion).status_code == 200
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    assert confirmar(seleccion).json()["ya_confirmada"] is True
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 2)


def test_rechazo_bonita_conserva_etapa_y_permite_reintentar(seleccion):
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    anterior = estado(seleccion[1])
    assert confirmar(seleccion).status_code == 409
    assert estado(seleccion[1]) == anterior
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 3
    seleccion[2]["caido"] = True
    assert confirmar(seleccion).status_code == 503
    assert estado(seleccion[1]) == anterior
    seleccion[2]["caido"] = False
    assert confirmar(seleccion).status_code == 200
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


def test_rechazo_al_ejecutar_tarea_permite_reintentar_sin_duplicar_aviso(seleccion, monkeypatch):
    from app.integrations.bonita.client import BonitaTaskConflictError

    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    ejecutar = bonita_client.ejecutar_tarea
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", AsyncMock(
        side_effect=BonitaTaskConflictError("Conflicto simulado")))
    anterior = estado_sin_intencion(seleccion[1])
    assert confirmar(seleccion).status_code == 409
    assert estado_sin_intencion(seleccion[1]) == anterior
    assert seleccion[2]["ejecuciones"] == []
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)
    assert confirmar(seleccion).status_code == 200
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 1)


def test_adjudicacion_individual_sin_opciones_conserva_contrato_y_confirma(seleccion):
    preparar_marcas(seleccion)
    respuesta = seleccion[0].post("/api/v1/ofertas/1/adjudicar", headers=cabecera(OPERADOR))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"oferta_id": 1, "mensaje": "Notificación de adjudicación enviada"}
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 2).status_code == 409
    assert adjudicar(seleccion, 1).status_code == 409
    assert adjudicar(seleccion, 2, True).status_code == 409
    assert estado(seleccion[1]) == anterior
    assert seleccion[3][1].call_count == 1
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    assert confirmar(seleccion).status_code == 200
    assert seleccion[2]["ejecuciones"] == [{"seleccionInput": PARES[:1]}]
    from app.models import AvisoAdjudicacion
    with seleccion[1]() as db:
        assert db.query(AvisoAdjudicacion).count() == 0
    assert seleccion[3][1].call_count == 1


def test_no_mezcla_adjudicacion_exclusiva_con_marcas(seleccion):
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1).status_code == 409
    assert adjudicar(seleccion, 2).status_code == 409
    assert estado(seleccion[1]) == anterior


@pytest.mark.parametrize("etapa", [EstadoEmergencia.ESPERA_LOTES, EstadoEmergencia.ESPERA_OFERTAS,
                                   EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA])
def test_nuevas_marcas_solo_en_esperando_adjudicacion(seleccion, etapa):
    preparar_marcas(seleccion)
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = etapa
        db.commit()
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1, True).status_code == 409
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("etapa", [EstadoEmergencia.ESPERA_LOTES, EstadoEmergencia.RESUELTA])
def test_confirmacion_no_abre_etapas_no_autorizadas(seleccion, etapa):
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = etapa
        db.commit()
    anterior = estado(seleccion[1])
    assert confirmar(seleccion).status_code == 409
    assert estado(seleccion[1]) == anterior
    assert seleccion[2]["ejecuciones"] == []


def test_reintento_reconcilia_commit_local_fallido(seleccion, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    clase_sesion = seleccion[1].class_
    commit = clase_sesion.commit
    fallos = [True]

    def guardar(db):
        if fallos and seleccion[2]["ejecuciones"]:
            fallos.pop()
            raise SQLAlchemyError("Fallo de commit simulado")
        return commit(db)

    monkeypatch.setattr(clase_sesion, "commit", guardar)
    anterior = estado_sin_intencion(seleccion[1])
    assert confirmar(seleccion).status_code == 503
    assert estado_sin_intencion(seleccion[1]) == anterior
    from app.models import AvisoAdjudicacion
    with seleccion[1]() as db:
        assert db.query(AvisoAdjudicacion).count() == 0
    seleccion[3][1].assert_not_called()
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200 and respuesta.json()["ya_confirmada"] is True
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 1)


def test_caida_despues_del_commit_recupera_aviso_en_sesion_nueva(seleccion_aislada, monkeypatch):
    from sqlalchemy import inspect
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    class CorteProceso(BaseException):
        pass

    seleccion = seleccion_aislada
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    sesiones = seleccion[1]
    commit = sesiones.class_.commit

    def guardar_y_caer(db):
        estado_final = any(isinstance(entidad, Emergencia)
                           and entidad.estado == EstadoEmergencia.EN_PROCESO
                           for entidad in db.identity_map.values())
        commit(db)
        if estado_final:
            raise CorteProceso()

    monkeypatch.setattr(sesiones.class_, "commit", guardar_y_caer)
    with sesiones() as db, pytest.raises(CorteProceso):
        asyncio.run(SeleccionOfertasService().confirmar(db, 2))
    monkeypatch.setattr(sesiones.class_, "commit", commit)
    seleccion[3][1].assert_not_called()
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
        assert "avisos_adjudicacion" in inspect(db.get_bind()).get_table_names()
        from app.models import AvisoAdjudicacion
        aviso = db.get(AvisoAdjudicacion, 1)
        assert aviso is not None and aviso.enviada_en is None
        creada_en = aviso.creada_en
    from app.services.notificaciones_adjudicacion_service import procesar_aviso_pendiente

    assert procesar_aviso_pendiente(sesiones) is True
    seleccion[3][1].assert_called_once()
    assert seleccion[3][1].call_args.args[-1] == creada_en
    assert confirmar(seleccion).status_code == 200
    assert procesar_aviso_pendiente(sesiones) is False
    with sesiones() as db:
        assert db.query(AvisoAdjudicacion).count() == 1
        assert db.get(AvisoAdjudicacion, 1).enviada_en is not None


@pytest.fixture(params=["sqlite", "postgresql"])
def seleccion_aislada(request, seleccion):
    if request.param == "sqlite":
        return seleccion
    from app.database import Base, get_db
    from app.main import app

    sesiones = request.getfixturevalue("sesiones_pg")
    with seleccion[1]() as origen, sesiones() as destino:
        for tabla in reversed(Base.metadata.sorted_tables):
            destino.execute(tabla.delete())
        for tabla in Base.metadata.sorted_tables:
            filas = [dict(fila) for fila in origen.execute(tabla.select()).mappings()]
            if filas:
                destino.execute(tabla.insert(), filas)
        destino.commit()

    def obtener_db():
        with sesiones() as db:
            yield db

    app.dependency_overrides[get_db] = obtener_db
    return seleccion[0], sesiones, seleccion[2], seleccion[3]


def test_aceptacion_remota_y_fallo_local_congelan_seleccion_entre_clientes(seleccion_aislada, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import SQLAlchemyError
    from app.main import app

    seleccion = seleccion_aislada
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    clase_sesion = seleccion[1].class_
    commit = clase_sesion.commit
    fallos = [True]

    def guardar(db):
        if fallos and seleccion[2]["ejecuciones"]:
            fallos.pop()
            raise SQLAlchemyError("Fallo local después de la aceptación remota")
        return commit(db)

    monkeypatch.setattr(clase_sesion, "commit", guardar)
    assert confirmar(seleccion).status_code == 503
    anterior = estado(seleccion[1])
    otro_cliente = TestClient(app)
    try:
        nueva = otro_cliente.post("/api/v1/ofertas/2/adjudicar?para_seleccion=true",
                                  headers=cabecera(OPERADOR))
        assert nueva.status_code == 409, nueva.text
        assert estado(seleccion[1]) == anterior
        assert adjudicar(seleccion, 1, True).status_code == 409
        reintento = otro_cliente.post(RUTA, headers=cabecera(OPERADOR))
        assert reintento.status_code == 200 and reintento.json()["ya_confirmada"] is True
    finally:
        otro_cliente.close()
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
        assert db.get(OfertaAyuda, 2).adjudicada_en is None
    assert seleccion[2]["seleccion"] == PARES[:1]
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 1)


def test_timeout_que_oculta_aceptacion_congela_y_reconcilia(seleccion_aislada, monkeypatch):
    from app.models import ConfirmacionSeleccion

    seleccion = seleccion_aislada
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    ejecutar = bonita_client.ejecutar_tarea

    async def perder_respuesta(*args, **kwargs):
        await ejecutar(*args, **kwargs)
        seleccion[2]["caido"] = True
        raise httpx.ReadTimeout("Aceptación remota sin respuesta ni reconciliación disponible")

    monkeypatch.setattr(bonita_client, "ejecutar_tarea", perder_respuesta)
    assert confirmar(seleccion).status_code == 503
    with seleccion[1]() as db:
        pendiente = db.get(ConfirmacionSeleccion, 2)
        assert pendiente.caso_id == "42"
        assert json.loads(pendiente.seleccion_json) == PARES[:1]
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 2, True).status_code == 409
    assert estado(seleccion[1]) == anterior
    seleccion[2]["caido"] = False
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200 and respuesta.json()["ya_confirmada"] is True
    with seleccion[1]() as db:
        assert db.get(ConfirmacionSeleccion, 2) is None
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 1)


@pytest.mark.parametrize("rechazo", ["evaluacion", "sin_conexion"])
def test_rechazo_antes_de_ejecutar_no_congela_nuevas_marcas(seleccion_aislada, rechazo):
    from app.models import ConfirmacionSeleccion

    seleccion = seleccion_aislada
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, 1, True).status_code == 200
    if rechazo == "evaluacion":
        seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    else:
        seleccion[2]["caido"] = True
    assert confirmar(seleccion).status_code == (409 if rechazo == "evaluacion" else 503)
    with seleccion[1]() as db:
        assert db.get(ConfirmacionSeleccion, 2) is None
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
    if rechazo == "sin_conexion":
        anterior = estado(seleccion[1])
        assert adjudicar(seleccion, 2, True).status_code == 503
        assert estado(seleccion[1]) == anterior
    seleccion[2]["caido"] = False
    assert adjudicar(seleccion, 2, True).status_code == 200
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 3
    assert confirmar(seleccion).status_code == 200
    assert seleccion[2]["seleccion"] == PARES
    assert len(seleccion[2]["ejecuciones"]) == 1
    comprobar_avisos_pendientes(seleccion, 2)


def test_create_all_agrega_intenciones_sin_reescribir_datos_previos(seleccion_aislada):
    from app.database import Base
    from app.models import ConfirmacionSeleccion

    sesiones = seleccion_aislada[1]
    with sesiones() as db:
        motor = db.get_bind()
    anterior = estado_sin_intencion(sesiones)
    ConfirmacionSeleccion.__table__.drop(motor)
    Base.metadata.create_all(motor)
    Base.metadata.create_all(motor)
    assert estado_sin_intencion(sesiones) == anterior
    with sesiones() as db:
        assert db.query(ConfirmacionSeleccion).count() == 0


def test_resuelta_con_confirmacion_previa_mantiene_idempotencia_sin_reabrir(seleccion):
    seleccion[2]["seleccion"] = PARES.copy()
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.RESUELTA
        db.commit()
    anterior = estado(seleccion[1])
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200 and respuesta.json()["ya_confirmada"] is True
    assert estado(seleccion[1]) == anterior
    assert seleccion[2]["ejecuciones"] == []


@pytest.mark.parametrize("rol,codigo", [(ONG, 403), (OPERADOR, 200), (AUDITOR, 403), (COORDINADOR, 403)])
def test_marcas_solo_las_hace_el_operador_municipal(seleccion, rol, codigo):
    preparar_marcas(seleccion)
    anterior = estado(seleccion[1])
    respuesta = adjudicar(seleccion, 1, True, rol)
    assert respuesta.status_code == codigo, respuesta.text
    if codigo == 403:
        assert estado(seleccion[1]) == anterior
        seleccion[3][1].assert_not_called()


def test_marcas_conservan_errores_de_entrada(seleccion):
    preparar_marcas(seleccion)
    cliente = seleccion[0]
    assert cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=true").status_code == 401
    assert adjudicar(seleccion, 999, True).status_code == 404
    assert cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=invalido",
                        headers=cabecera(OPERADOR)).status_code == 422
    with seleccion[1]() as db:
        oferta = db.get(OfertaAyuda, 2)
        oferta.items.clear()
        db.commit()
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 2, True).status_code == 400
    assert estado(seleccion[1]) == anterior


def test_confirma_ofertas_completas_y_reintento_sin_duplicar_correo(seleccion):
    _, sesiones, motor, dobles = seleccion
    respuesta = confirmar(seleccion)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"emergencia_id": 2, "cantidad_pares": 2, "ya_confirmada": False}
    assert motor["ejecuciones"] == [{"seleccionInput": PARES}]
    assert motor["asignaciones"] == [{"assigned_id": "12"}]
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    anterior = estado(sesiones)
    motor["seleccion"].reverse()
    motor["archivado"] = True
    reintento = confirmar(seleccion)
    assert reintento.status_code == 200 and reintento.json()["ya_confirmada"] is True
    assert len(motor["ejecuciones"]) == 1
    assert estado(sesiones) == anterior
    comprobar_avisos_pendientes(seleccion, 2)


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
    with seleccion[1]() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO


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
    emergencia = SimpleNamespace(id=2, bonita_case_id="42", estado=EstadoEmergencia.EN_PROCESO)
    ofertas = [SimpleNamespace(id=numero, adjudicada_en=True, items=[SimpleNamespace(
        lote_necesidad_id=2, cantidad_ofrecida=3, lote_necesidad=SimpleNamespace(emergencia_id=2))])
        for numero in (1, 2)]
    monkeypatch.setattr("app.services.seleccion_ofertas_service.EmergenciaRepository.obtener_por_id",
                        lambda *args, **kwargs: emergencia)
    monkeypatch.setattr("app.services.seleccion_ofertas_service.OfertaRepository.listar_de_emergencia",
                        lambda *args, **kwargs: ofertas)
    monkeypatch.setattr("app.services.evaluacion_cloud_service.EvaluacionCloudService.ultima",
                        lambda *args, **kwargs: None)
    motor = seleccion[2]
    motor["concurrente"] = True

    def confirmar_en_sesion(_):
        db = Mock()
        pendientes = []
        db.get.side_effect = lambda *args, **kwargs: next(iter(pendientes), None)
        db.add.side_effect = pendientes.append
        db.delete.side_effect = pendientes.remove
        return asyncio.run(SeleccionOfertasService().confirmar(db, 2))

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        respuestas = list(ejecutor.map(confirmar_en_sesion, range(2)))
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
        resultados = [primera.result(timeout=10), segunda.result(timeout=10)]
        assert sorted(respuesta.ya_confirmada for respuesta in resultados) == [False, True]
    ejecucion.assert_awaited_once()
    from app.models import AvisoAdjudicacion
    with sesiones_pg() as db:
        assert db.query(AvisoAdjudicacion).count() == 1


@pytest.mark.parametrize("operacion", ["adjudicar", "editar"])
def test_confirmacion_congela_ofertas_sin_invertir_bloqueos(sesiones_pg, monkeypatch, operacion):
    from fastapi import BackgroundTasks, HTTPException
    from app.repositories import OfertaRepository
    from app.schemas import OfertaActualizar
    from app.services.ofertas_service import OfertaService
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.bonita_case_id = "42"
        emergencia.estado = (EstadoEmergencia.ESPERANDO_ADJUDICACION if operacion == "adjudicar"
                             else EstadoEmergencia.ESPERA_OFERTAS)
        oferta = db.get(OfertaAyuda, 1)
        oferta.adjudicada_en = datetime.now(timezone.utc)
        oferta.items = [OfertaItem(lote_necesidad_id=1, cantidad_ofrecida=3)]
        db.add(OfertaAyuda(id=2, emergencia_id=1, organizacion_id=1,
                          items=[OfertaItem(lote_necesidad_id=1, cantidad_ofrecida=3)]))
        db.commit()

    emergencia_bloqueada, segunda_esperando, continuar = Event(), Event(), Event()
    listar = OfertaRepository.listar_de_emergencia

    def listar_pausado(*args, **kwargs):
        emergencia_bloqueada.set()
        assert continuar.wait(5)
        return listar(*args, **kwargs)

    monkeypatch.setattr(OfertaRepository, "listar_de_emergencia", listar_pausado)
    servicio = OfertaService()
    obtener = servicio._emergencias.obtener_emergencia_entidad

    def obtener_pausado(*args, **kwargs):
        segunda_esperando.set()
        return obtener(*args, **kwargs)

    monkeypatch.setattr(servicio._emergencias, "obtener_emergencia_entidad", obtener_pausado)
    guardada = []

    async def variable(caso_id, nombre):
        return json.dumps(guardada if nombre == "seleccionOfertasJson" else {
            "emergencia_id": 1, "resultados": [
                {"oferta_id": 1, "lote_id": 1, "cantidad_verificada": 3}]})

    async def ejecutar(tarea_id, contrato):
        guardada.extend(contrato["seleccionInput"])

    monkeypatch.setattr(bonita_client, "obtener_variable_caso", variable)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value={
        "id": "99", "caseId": "42", "name": "Seleccionar oferta", "actorId": "7", "assigned_id": "12"}))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", AsyncMock(side_effect=ejecutar))

    def confirmar_en_sesion():
        with sesiones_pg() as db:
            return asyncio.run(SeleccionOfertasService().confirmar(db, 1))

    def cambiar_en_sesion():
        with sesiones_pg() as db:
            with pytest.raises(HTTPException) as error:
                if operacion == "adjudicar":
                    servicio.adjudicar_oferta(db, 2, BackgroundTasks(), para_seleccion=True)
                else:
                    servicio.actualizar_oferta(db, 2, OfertaActualizar(observaciones="No debe guardarse"))
            assert error.value.status_code == 409

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        confirmacion = ejecutor.submit(confirmar_en_sesion)
        assert emergencia_bloqueada.wait(5)
        cambio = ejecutor.submit(cambiar_en_sesion)
        try:
            assert segunda_esperando.wait(5)
            with pytest.raises(TimeoutError):
                cambio.result(timeout=0.1)
        finally:
            continuar.set()
        assert confirmacion.result(timeout=10).cantidad_pares == 1
        cambio.result(timeout=10)
    assert guardada == [{"oferta_id": 1, "lote_id": 1}]
    with sesiones_pg() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.EN_PROCESO
        assert db.get(OfertaAyuda, 2).adjudicada_en is None
        assert db.get(OfertaAyuda, 2).observaciones is None


@pytest.mark.parametrize("rol,codigo", [(ONG, 403), (OPERADOR, 200), (AUDITOR, 403), (COORDINADOR, 403)])
def test_confirmar_solo_lo_hace_el_operador_municipal(seleccion, rol, codigo):
    anterior = estado(seleccion[1])
    respuesta = confirmar(seleccion, rol)
    assert respuesta.status_code == codigo, respuesta.text
    if codigo == 403:
        assert estado(seleccion[1]) == anterior
        assert seleccion[2]["ejecuciones"] == []


def test_sin_autenticacion_y_emergencia_inexistente(seleccion):
    cliente = seleccion[0]
    assert cliente.post(RUTA).status_code == 401
    assert cliente.post(RUTA.replace("/2/", "/999/"), headers=cabecera(OPERADOR)).status_code == 404


# --- Adjudicación por el municipio (OPERADOR_MUNICIPAL) ---

@pytest.mark.parametrize("rol", [COORDINADOR, AUDITOR])
@pytest.mark.parametrize("para_seleccion", [False, True])
def test_coordinador_y_auditor_no_adjudican(seleccion, rol, para_seleccion):
    preparar_marcas(seleccion)
    anterior = estado(seleccion[1])
    assert adjudicar(seleccion, 1, para_seleccion, rol).status_code == 403
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


def test_operador_adjudica_oferta_validada(seleccion):
    preparar_marcas(seleccion)
    respuesta = adjudicar(seleccion, 1)
    assert respuesta.status_code == 200, respuesta.text
    with seleccion[1]() as db:
        assert db.get(OfertaAyuda, 1).adjudicada_en is not None


@pytest.mark.parametrize("para_seleccion", [False, True])
def test_adjudicar_oferta_no_validada_responde_409(seleccion, para_seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    anterior = estado(seleccion[1])
    respuesta = adjudicar(seleccion, 1, para_seleccion)
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["detail"] == "La oferta no fue validada por el Sistema Nacional"
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


def test_operador_lista_solo_ofertas_validadas(seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["evaluacion"]["resultados"][1]["cantidad_verificada"] = 0
    operador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(OPERADOR))
    assert operador.status_code == 200, operador.text
    assert [o["id"] for o in operador.json()] == [1]
    assert all(item["cantidad_verificada"] > 0 for o in operador.json() for item in o["items"])
    coordinador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert sorted(o["id"] for o in coordinador.json()) == [1, 2]


def test_operador_sin_evaluacion_nacional_recibe_lista_vacia(seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["evaluacion"] = None
    operador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(OPERADOR))
    assert operador.status_code == 200, operador.text
    assert operador.json() == []
    coordinador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert sorted(o["id"] for o in coordinador.json()) == [1, 2]


MENSAJE_EN_EVALUACION = ("La emergencia está en evaluación del Centro Coordinador: "
                         "la cobertura no alcanzó y todavía no se puede adjudicar")


@pytest.mark.parametrize("para_seleccion", [False, True])
@pytest.mark.parametrize("cambio", ["evaluando", "sin_seleccion"])
def test_adjudicar_en_evaluar_proyecto_responde_409_sin_marcar(seleccion, para_seleccion, cambio):
    preparar_marcas(seleccion)
    if cambio == "evaluando":
        seleccion[2]["evaluando"] = True
    else:
        # Camino alternativo: Seleccionar oferta nunca se habilitó.
        seleccion[2]["evaluando"] = True
        seleccion[2]["tarea"] = None
    anterior = estado(seleccion[1])
    respuesta = adjudicar(seleccion, 1, para_seleccion)
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["detail"] == MENSAJE_EN_EVALUACION
    assert estado(seleccion[1]) == anterior
    with seleccion[1]() as db:
        assert db.get(OfertaAyuda, 1).adjudicada_en is None
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("para_seleccion", [False, True])
def test_adjudicar_con_seleccionar_oferta_lista(seleccion, para_seleccion):
    preparar_marcas(seleccion)
    respuesta = adjudicar(seleccion, 1, para_seleccion)
    assert respuesta.status_code == 200, respuesta.text
    with seleccion[1]() as db:
        assert db.get(OfertaAyuda, 1).adjudicada_en is not None


@pytest.mark.parametrize("para_seleccion", [False, True])
def test_bonita_caido_al_adjudicar_responde_503(seleccion, para_seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["caido"] = True
    anterior = estado(seleccion[1])
    respuesta = adjudicar(seleccion, 1, para_seleccion)
    assert respuesta.status_code == 503, respuesta.text
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("etapa", [EstadoEmergencia.ESPERANDO_ADJUDICACION, EstadoEmergencia.EN_PROCESO])
def test_operador_con_caso_en_evaluacion_recibe_lista_vacia(seleccion, etapa):
    preparar_marcas(seleccion)
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = etapa
        db.commit()
    seleccion[2]["evaluando"] = True
    operador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(OPERADOR))
    assert operador.status_code == 200, operador.text
    assert operador.json() == []
    coordinador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(COORDINADOR))
    assert sorted(o["id"] for o in coordinador.json()) == [1, 2]


def test_operador_sin_seleccionar_oferta_lista_recibe_lista_vacia(seleccion):
    preparar_marcas(seleccion)
    seleccion[2]["tarea"] = None
    operador = seleccion[0].get("/api/v1/emergencias/2/ofertas", headers=cabecera(OPERADOR))
    assert operador.status_code == 200 and operador.json() == []
