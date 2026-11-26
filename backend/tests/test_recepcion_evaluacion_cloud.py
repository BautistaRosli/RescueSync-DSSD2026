"""Recepción municipal aislada: no se ejecutan servicios de negocio externos."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException

from app.integrations.bonita.client import bonita_client
from app.models import Emergencia, EstadoEmergencia, LoteRecursoCloud, OfertaAyuda, OrganizacionCloud
from app.services.curso_accion_service import CursoAccionService
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno, estado
from test_concurrencia import sesiones_pg

RUTA = "/api/v1/emergencias/2"


@pytest.fixture
def recepcion(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    with sesiones() as db:
        db.get(Emergencia, 2).bonita_case_id = "42"
        db.add_all([LoteRecursoCloud(lote_id=2, tipo_recurso_id=41),
                    OrganizacionCloud(organizacion_id=1, ong_id=901),
                    OrganizacionCloud(organizacion_id=2, ong_id=907)])
        db.commit()
    monkeypatch.setattr(bonita_client, "obtener_variable_caso", AsyncMock(return_value=None))
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value={
        "id": "99", "caseId": "42", "name": "Seleccionar oferta", "state": "ready"}))
    return cliente, sesiones


def preparar(cliente):
    respuesta = cliente.post(f"{RUTA}/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def cuerpo(envelope):
    return {"solicitud_id": envelope["solicitud_id"], "caso_id": envelope["caso_id"],
            "evaluacion": {"emergencia_id": 2, "resultados": [
                {"oferta_id": 1, "lote_id": 2, "cantidad_ofrecida": 5, "cantidad_verificada": 3,
                 "es_consorcio": False, "nivel_habilitacion": "PARCIAL", "cobertura_lote_pct": 30.0,
                 "participantes": [{"ong_id": 901, "rol": "PRINCIPAL", "habilitada": True,
                     "capacidades_habilitadas": [{"tipo_recurso_id": 41, "cantidad_ofrecida": 5,
                                                   "cantidad_verificada": 3}],
                     "observaciones": {"detalle": "Stock verificado", "faltantes": [2]}}],
                 "observaciones": ["Agua disponible"]}],
                "observaciones": ["Cobertura parcial"], "metadatos": {"version": 1}}}


def recibir(cliente, data, rol=COORDINADOR):
    return cliente.post(f"{RUTA}/evaluacion-cloud", headers=cabecera(rol) if rol else {}, json=data)


def test_persistencia_completa_y_seleccion_sin_variable(recepcion):
    from app.models import EvaluacionCloud

    cliente, sesiones = recepcion
    envelope = preparar(cliente)
    assert set(envelope) == {"solicitud_id", "caso_id", "solicitud"}
    assert envelope["caso_id"] == 42
    assert preparar(cliente) == envelope
    data = cuerpo(envelope)
    assert recibir(cliente, data).status_code == 204
    with sesiones() as db:
        guardada = db.query(EvaluacionCloud).one()
        assert json.loads(guardada.evaluacion_json) == data["evaluacion"]
        assert json.loads(guardada.solicitud_json) == envelope["solicitud"]
    listado = cliente.get(f"{RUTA}/ofertas", headers=cabecera(COORDINADOR))
    assert listado.status_code == 200
    assert listado.json()[0]["items"][0]["cantidad_verificada"] == 3
    assert listado.json()[0]["puede_seleccionar"] is True
    seleccion = cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=true", headers=cabecera(OPERADOR))
    assert seleccion.status_code == 200, seleccion.text
    anterior = estado(sesiones)
    assert recibir(cliente, data).status_code == 204
    assert estado(sesiones) == anterior
    cambiada = copy.deepcopy(data)
    cambiada["evaluacion"]["resultados"][0]["cantidad_verificada"] = 2
    assert recibir(cliente, cambiada).status_code == 409
    bonita_client.obtener_variable_caso.assert_not_awaited()


def test_reintento_distingue_booleanos_y_numeros_en_extras(recepcion):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    data["evaluacion"]["metadatos"]["indicador"] = True
    assert recibir(cliente, data).status_code == 204
    anterior = estado(sesiones)
    data["evaluacion"]["metadatos"]["indicador"] = 1
    assert recibir(cliente, data).status_code == 409
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("cambio", ["caso", "emergencia", "token", "duplicado", "faltante", "ajeno"])
def test_rechazo_no_altera_datos(recepcion, cambio):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    if cambio == "caso":
        data["caso_id"] = 43
    elif cambio == "emergencia":
        data["evaluacion"]["emergencia_id"] = 1
    elif cambio == "token":
        data["solicitud_id"] = "otra-ronda"
    elif cambio == "duplicado":
        data["evaluacion"]["resultados"] *= 2
    elif cambio == "faltante":
        data["evaluacion"]["resultados"] = []
    else:
        data["evaluacion"]["resultados"][0]["oferta_id"] = 999
    anterior = estado(sesiones)
    assert recibir(cliente, data).status_code == 409
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("cantidad", [True, -1, 1.5, "3", None])
def test_cantidades_estrictas(recepcion, cantidad):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    data["evaluacion"]["resultados"][0]["cantidad_verificada"] = cantidad
    anterior = estado(sesiones)
    assert recibir(cliente, data).status_code == 422
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("rol,codigo", [(ONG, 403), (OPERADOR, 403), (None, 401)])
@pytest.mark.parametrize("operacion", ["solicitud-evaluacion", "evaluacion-cloud"])
def test_autorizacion(recepcion, rol, codigo, operacion):
    cliente, sesiones = recepcion
    anterior = estado(sesiones)
    respuesta = cliente.post(f"{RUTA}/{operacion}", headers=cabecera(rol) if rol else {},
                             json={"solicitud_id": "token", "caso_id": 42,
                                   "evaluacion": {"emergencia_id": 2, "resultados": []}})
    assert respuesta.status_code == codigo
    assert estado(sesiones) == anterior


def test_pendiente_no_reutiliza_variable_y_respeta_tarea(recepcion):
    cliente, _ = recepcion
    data = cuerpo(preparar(cliente))
    bonita_client.obtener_variable_caso.return_value = json.dumps(data["evaluacion"])
    listado = cliente.get(f"{RUTA}/ofertas", headers=cabecera(COORDINADOR)).json()
    assert listado[0]["items"][0]["cantidad_verificada"] is None
    assert cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=true", headers=cabecera(OPERADOR)).status_code == 409
    assert recibir(cliente, data, AUDITOR).status_code == 204
    bonita_client.obtener_tarea_pendiente.return_value = None
    assert cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=true", headers=cabecera(OPERADOR)).status_code == 409
    bonita_client.obtener_variable_caso.assert_not_awaited()


@pytest.mark.parametrize("accion", ["REABRIR", "REFORMULAR"])
def test_ronda_vieja_no_regresa_al_reabrir(recepcion, accion):
    from app.models import EvaluacionCloud

    cliente, sesiones = recepcion
    vieja = cuerpo(preparar(cliente))
    assert recibir(cliente, vieja).status_code == 204
    with sesiones() as db:
        CursoAccionService().aplicar(db, 2, accion)
    anterior = estado(sesiones)
    assert recibir(cliente, vieja).status_code == 409
    assert estado(sesiones) == anterior
    with sesiones() as db:
        emergencia = db.get(Emergencia, 2)
        emergencia.estado = EstadoEmergencia.ESPERA_OFERTAS
        emergencia.publicada = True
        db.commit()
    nueva = cuerpo(preparar(cliente))
    assert nueva["solicitud_id"] != vieja["solicitud_id"]
    assert recibir(cliente, vieja).status_code == 409
    assert recibir(cliente, nueva).status_code == 204
    with sesiones() as db:
        assert db.query(EvaluacionCloud).count() == 2


def test_callback_sin_ronda_y_despues_de_adjudicacion(recepcion):
    cliente, sesiones = recepcion
    data = cuerpo({"solicitud_id": "inexistente", "caso_id": 42})
    assert recibir(cliente, data).status_code == 409
    data = cuerpo(preparar(cliente))
    with sesiones() as db:
        db.get(OfertaAyuda, 1).adjudicada_en = datetime.now(timezone.utc)
        db.commit()
    assert recibir(cliente, data).status_code == 409


def test_error_commit_libera_transaccion(recepcion, monkeypatch):
    from sqlalchemy.orm import Session
    from app.models import EvaluacionCloud

    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    original = Session.commit
    def fallar(db):
        raise SQLAlchemyError("fallo simulado")
    monkeypatch.setattr(Session, "commit", fallar)
    assert recibir(cliente, data).status_code == 503
    monkeypatch.setattr(Session, "commit", original)
    with sesiones() as db:
        assert db.query(EvaluacionCloud).one().evaluacion_json is None
    assert recibir(cliente, data).status_code == 204


def test_sin_ofertas_y_cantidad_cero_son_resultados_validos(recepcion):
    from app.models import OfertaItem

    cliente, sesiones = recepcion
    with sesiones() as db:
        db.query(OfertaItem).delete()
        db.commit()
    data = cuerpo(preparar(cliente))
    data["evaluacion"]["resultados"] = []
    assert recibir(cliente, data).status_code == 204


def test_cero_verificado_se_conserva_y_no_habilita_seleccion(recepcion):
    cliente, _ = recepcion
    data = cuerpo(preparar(cliente))
    data["evaluacion"]["resultados"][0]["cantidad_verificada"] = 0
    assert recibir(cliente, data).status_code == 204
    listado = cliente.get(f"{RUTA}/ofertas", headers=cabecera(COORDINADOR)).json()
    assert listado[0]["items"][0]["cantidad_verificada"] == 0
    assert listado[0]["puede_seleccionar"] is False


@pytest.mark.parametrize("campo", ["metadatos", "cantidad_verificada", "caso_id"])
def test_campo_no_finito_se_rechaza_sin_escritura(recepcion, campo):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    if campo == "metadatos":
        data["evaluacion"]["metadatos"]["valor"] = float("nan")
    elif campo == "caso_id":
        data["caso_id"] = float("nan")
    else:
        data["evaluacion"]["resultados"][0][campo] = float("nan")
    anterior = estado(sesiones)
    respuesta = cliente.post(f"{RUTA}/evaluacion-cloud", content=json.dumps(data),
                             headers={**cabecera(COORDINADOR), "Content-Type": "application/json"})
    assert respuesta.status_code == 422
    assert estado(sesiones) == anterior


def test_confirmacion_usa_evaluacion_local(recepcion, monkeypatch):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    assert recibir(cliente, data).status_code == 204
    assert cliente.post("/api/v1/ofertas/1/adjudicar?para_seleccion=true", headers=cabecera(OPERADOR)).status_code == 200
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    bonita_client.obtener_tarea_pendiente.return_value.update({"actorId": "7", "assigned_id": "0"})
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", AsyncMock())
    respuesta = cliente.post(f"{RUTA}/confirmar-seleccion", headers=cabecera(OPERADOR))
    assert respuesta.status_code == 200, respuesta.text
    assert all(llamada.args[1] == "seleccionOfertasJson"
               for llamada in bonita_client.obtener_variable_caso.await_args_list)
    with sesiones() as db:
        assert db.get(Emergencia, 2).estado == EstadoEmergencia.EN_PROCESO
    assert recibir(cliente, data).status_code == 204


def test_legacy_sigue_leyendo_variable(recepcion):
    cliente, sesiones = recepcion
    with sesiones() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        db.commit()
    bonita_client.obtener_variable_caso.return_value = json.dumps(cuerpo({"solicitud_id": "legacy", "caso_id": 42})["evaluacion"])
    listado = cliente.get(f"{RUTA}/ofertas", headers=cabecera(COORDINADOR)).json()
    assert listado[0]["items"][0]["cantidad_verificada"] == 3
    bonita_client.obtener_variable_caso.assert_awaited_once_with(42, "evaluacionJson")


@pytest.mark.parametrize("campo,valor", [("oferta_id", True), ("lote_id", "2"),
                                        ("cantidad_ofrecida", 4), ("cantidad_verificada", 6)])
def test_snapshot_e_identificadores_estrictos(recepcion, campo, valor):
    cliente, sesiones = recepcion
    data = cuerpo(preparar(cliente))
    data["evaluacion"]["resultados"][0][campo] = valor
    anterior = estado(sesiones)
    assert recibir(cliente, data).status_code == (422 if campo in ("oferta_id", "lote_id") else 409)
    assert estado(sesiones) == anterior


def preparar_pg(sesiones_pg):
    from app.services.solicitud_evaluacion_service import SolicitudEvaluacionService

    with sesiones_pg() as db:
        db.get(Emergencia, 1).bonita_case_id = "42"
        db.get(Emergencia, 1).publicada = True
        db.add_all([LoteRecursoCloud(lote_id=lote, tipo_recurso_id=41) for lote in (1, 2)])
        db.add(OrganizacionCloud(organizacion_id=1, ong_id=901))
        db.commit()
        return SolicitudEvaluacionService().preparar(db, 1)


def test_pg_callbacks_concurrentes_no_sobrescriben(sesiones_pg):
    from app.models import EvaluacionCloud
    from app.schemas.evaluacion_cloud_schema import RecepcionEvaluacionCloud
    from app.services.evaluacion_cloud_service import EvaluacionCloudService

    ronda = preparar_pg(sesiones_pg)
    barrera = Barrier(2)
    def enviar(numero):
        datos = RecepcionEvaluacionCloud(solicitud_id=ronda["solicitud_id"], caso_id=42,
            evaluacion={"emergencia_id": 1, "resultados": [], "observaciones": [str(numero)]})
        with sesiones_pg() as db:
            barrera.wait(timeout=5)
            try:
                EvaluacionCloudService().recibir(db, 1, datos)
                return 204, numero
            except HTTPException as exc:
                return exc.status_code, numero
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(enviar, (1, 2)))
    assert sorted(codigo for codigo, _ in resultados) == [204, 409]
    ganador = next(numero for codigo, numero in resultados if codigo == 204)
    with sesiones_pg() as db:
        assert json.loads(db.query(EvaluacionCloud).one().evaluacion_json)["observaciones"] == [str(ganador)]


def test_pg_callback_encolado_revalida_ronda_tras_reabrir(sesiones_pg):
    from app.models import EvaluacionCloud
    from app.repositories import EmergenciaRepository
    from app.schemas.evaluacion_cloud_schema import RecepcionEvaluacionCloud
    from app.services.evaluacion_cloud_service import EvaluacionCloudService

    ronda = preparar_pg(sesiones_pg)
    datos = RecepcionEvaluacionCloud(solicitud_id=ronda["solicitud_id"], caso_id=42,
                                    evaluacion={"emergencia_id": 1, "resultados": []})
    iniciada = Event()
    def enviar():
        with sesiones_pg() as db:
            iniciada.set()
            try:
                EvaluacionCloudService().recibir(db, 1, datos)
                return 204
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        with sesiones_pg() as db:
            EmergenciaRepository().obtener_por_id(db, 1, bloquear=True)
            futuro = ejecutor.submit(enviar)
            assert iniciada.wait(5)
            CursoAccionService().aplicar(db, 1, "REABRIR")
        assert futuro.result(timeout=10) == 409
    with sesiones_pg() as db:
        assert db.query(EvaluacionCloud).one().evaluacion_json is None
