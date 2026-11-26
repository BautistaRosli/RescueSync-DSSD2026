"""Evaluación del proyecto desde RescueSync, sin ejecutar casos reales."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.bonita.client import (
    BonitaClientError,
    BonitaTaskConflictError,
    bonita_client,
)
from app.models import ConfirmacionSeleccion, CursoAccionEmergencia, Emergencia, EstadoEmergencia, OfertaAyuda
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno, estado
from test_concurrencia import sesiones_pg

RUTA = "/api/v1/emergencias/1/evaluacion-proyecto"
TAREA = {"id": "101", "caseId": "42", "name": "Evaluar proyecto",
         "actorId": "7", "assigned_id": "0", "state": "ready"}


@pytest.fixture
def evaluacion(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.publicada = True
        emergencia.estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        emergencia.bonita_case_id = "42"
        db.commit()
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=dict(TAREA)))
    monkeypatch.setattr(bonita_client, "tarea_completada", AsyncMock(return_value=False))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", AsyncMock())
    return cliente, sesiones


def decidir(cliente, accion="REABRIR", tarea_id=101):
    return cliente.post(RUTA, headers=cabecera(COORDINADOR), json={"tarea_id": tarea_id, "accion": accion})


def test_consultar_tarea_sin_ofertas_no_cambia_datos(evaluacion):
    cliente, sesiones = evaluacion
    anterior = estado(sesiones)
    respuesta = cliente.get(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"tarea_id": 101}
    assert estado(sesiones) == anterior
    bonita_client.obtener_tarea_pendiente.assert_awaited_once_with(42, "Evaluar proyecto")
    bonita_client.ejecutar_tarea.assert_not_awaited()


@pytest.mark.parametrize("evaluar,seleccionar,lista", [(True, True, False), (False, True, True),
                                                      (False, False, False)])
def test_consultar_incluye_seleccion_solo_cuando_la_etapa_llego(evaluacion, evaluar, seleccionar, lista):
    cliente, sesiones = evaluacion
    anterior = estado(sesiones)

    async def consultar(caso_id, nombre):
        assert caso_id == 42
        if nombre == "Evaluar proyecto":
            return dict(TAREA) if evaluar else None
        assert nombre == "Seleccionar oferta"
        return {**TAREA, "id": "102", "name": nombre} if seleccionar else None

    bonita_client.obtener_tarea_pendiente.side_effect = consultar
    respuesta = cliente.get(RUTA, params={"incluir_seleccion": True}, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"tarea_id": 101 if evaluar else None, "seleccion_oferta_lista": lista}
    assert estado(sesiones) == anterior
    bonita_client.ejecutar_tarea.assert_not_awaited()


@pytest.mark.parametrize("cambios,codigo", [({"state": "initializing"}, 200),
                                           ({"caseId": "99"}, 409), ({"name": "Otra"}, 409),
                                           ({"id": "invalido"}, 503)])
def test_consulta_seleccion_valida_identidad_y_ready(evaluacion, cambios, codigo):
    cliente, _ = evaluacion
    bonita_client.obtener_tarea_pendiente.side_effect = [None, {**TAREA, "name": "Seleccionar oferta", **cambios}]
    respuesta = cliente.get(RUTA, params={"incluir_seleccion": True}, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == codigo, respuesta.text
    if codigo == 200:
        assert respuesta.json() == {"tarea_id": None, "seleccion_oferta_lista": False}


def test_consulta_seleccion_fuera_de_fase_es_false(evaluacion):
    cliente, sesiones = evaluacion
    with sesiones() as db:
        db.get(Emergencia, 1).estado = EstadoEmergencia.EN_PROCESO
        db.commit()
    respuesta = cliente.get(RUTA, params={"incluir_seleccion": True}, headers=cabecera(COORDINADOR))
    assert respuesta.json() == {"tarea_id": None, "seleccion_oferta_lista": False}
    bonita_client.obtener_tarea_pendiente.assert_not_awaited()


@pytest.mark.parametrize("accion", ["REABRIR", "REFORMULAR", "CONTINUAR_PARCIAL"])
def test_ejecuta_solo_tarea_y_contrato_de_evaluacion(evaluacion, accion):
    cliente, sesiones = evaluacion
    anterior = estado(sesiones)
    respuesta = decidir(cliente, accion)
    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.json() == {"tarea_id": 101}
    bonita_client.obtener_miembro_actor.assert_awaited_once_with(7, solo_usuarios=True)
    bonita_client.asignar_tarea.assert_awaited_once_with(101, 12)
    bonita_client.ejecutar_tarea.assert_awaited_once_with(101, {"accionInput": accion})
    assert estado(sesiones) == anterior  # Sólo el conector aplica el resultado local.


@pytest.mark.parametrize("rol,codigo", [(OPERADOR, 403), (ONG, 403), (AUDITOR, 403), (None, 401)])
@pytest.mark.parametrize("metodo", ["GET", "POST"])
def test_solo_coordinador_ejecuta_y_consulta(evaluacion, rol, codigo, metodo):
    cliente, sesiones = evaluacion
    anterior = estado(sesiones)
    respuesta = cliente.request(metodo, RUTA, headers=cabecera(rol) if rol else {},
                                json={"tarea_id": 101, "accion": "REABRIR"} if metodo == "POST" else None)
    assert respuesta.status_code == codigo
    assert estado(sesiones) == anterior
    bonita_client.obtener_tarea_pendiente.assert_not_awaited()


@pytest.mark.parametrize("cambios", [
    {"estado": EstadoEmergencia.ESPERA_OFERTAS}, {"estado": EstadoEmergencia.ESPERA_LOTES},
    {"estado": EstadoEmergencia.EN_PROCESO}, {"estado": EstadoEmergencia.RESUELTA},
    {"publicada": False}, {"bonita_case_id": None},
])
def test_fuera_de_etapa_no_hay_evaluacion(evaluacion, cambios):
    cliente, sesiones = evaluacion
    with sesiones() as db:
        for atributo, valor in cambios.items():
            setattr(db.get(Emergencia, 1), atributo, valor)
        db.commit()
    assert cliente.get(RUTA, headers=cabecera(COORDINADOR)).json() == {"tarea_id": None}
    assert decidir(cliente).status_code == 409
    bonita_client.obtener_tarea_pendiente.assert_not_awaited()


@pytest.mark.parametrize("cambios", [{"id": "201"}, {"caseId": "99"},
                                    {"name": "Adjudicar ofertas"}, {"state": "completed"}, {"state": None}])
def test_rechaza_tarea_obsoleta_o_ajena_sin_efectos(evaluacion, cambios):
    cliente, sesiones = evaluacion
    bonita_client.obtener_tarea_pendiente.return_value = {**TAREA, **cambios}
    anterior = estado(sesiones)
    assert decidir(cliente).status_code == 409
    bonita_client.asignar_tarea.assert_not_awaited()
    bonita_client.ejecutar_tarea.assert_not_awaited()
    assert estado(sesiones) == anterior


def test_no_hay_tarea_lista(evaluacion):
    cliente, _ = evaluacion
    bonita_client.obtener_tarea_pendiente.return_value = None
    assert cliente.get(RUTA, headers=cabecera(COORDINADOR)).json() == {"tarea_id": None}
    assert decidir(cliente).status_code == 409
    bonita_client.ejecutar_tarea.assert_not_awaited()


@pytest.mark.parametrize("estado", ["initializing", "executing", "completed"])
def test_consultar_tarea_transitoria_devuelve_null(evaluacion, estado):
    cliente, _ = evaluacion
    bonita_client.obtener_tarea_pendiente.return_value = {**TAREA, "state": estado}
    respuesta = cliente.get(RUTA, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"tarea_id": None}
    bonita_client.ejecutar_tarea.assert_not_awaited()


@pytest.mark.parametrize("cuerpo", [{}, {"accion": "REABRIR"}, {"tarea_id": 101},
    {"tarea_id": 101, "accion": "OTRA"}, {"tarea_id": 101, "accion": "reabrir"},
    {"tarea_id": -1, "accion": "REABRIR"}, {"tarea_id": True, "accion": "REABRIR"},
    {"tarea_id": "101", "accion": "REABRIR"}, {"tarea_id": 1.5, "accion": "REABRIR"},
    {"tarea_id": 101, "accion": "REABRIR", "caso_id": 42}])
def test_contrato_rechaza_cuerpos_invalidos(evaluacion, cuerpo):
    cliente, _ = evaluacion
    assert cliente.post(RUTA, headers=cabecera(COORDINADOR), json=cuerpo).status_code == 422
    bonita_client.obtener_tarea_pendiente.assert_not_awaited()


@pytest.mark.parametrize("pendiente", [False, True])
@pytest.mark.parametrize("accion", ["REABRIR", "REFORMULAR"])
def test_retroceso_rechaza_seleccion_preexistente(evaluacion, pendiente, accion):
    cliente, sesiones = evaluacion
    with sesiones() as db:
        if pendiente:
            db.add(ConfirmacionSeleccion(emergencia_id=1, caso_id="42", seleccion_json="[]"))
        else:
            db.add(OfertaAyuda(emergencia_id=1, organizacion_id=1, adjudicada_en=datetime.now(timezone.utc)))
        db.commit()
    assert decidir(cliente, accion).status_code == 409
    bonita_client.ejecutar_tarea.assert_not_awaited()


def test_respeta_asignacion_existente(evaluacion):
    cliente, _ = evaluacion
    bonita_client.obtener_tarea_pendiente.return_value = {**TAREA, "assigned_id": "99"}
    assert decidir(cliente).status_code == 202
    bonita_client.obtener_miembro_actor.assert_not_awaited()
    bonita_client.asignar_tarea.assert_not_awaited()


@pytest.mark.parametrize("miembro", [None, {}, {"user_id": "0"}, {"user_id": "invalido"}])
def test_actor_sin_usuario_directo_no_ejecuta(evaluacion, miembro):
    cliente, _ = evaluacion
    bonita_client.obtener_miembro_actor.return_value = miembro
    assert decidir(cliente).status_code == 503
    bonita_client.ejecutar_tarea.assert_not_awaited()


@pytest.mark.parametrize("operacion", ["obtener_tarea_pendiente", "tarea_completada", "asignar_tarea", "ejecutar_tarea"])
@pytest.mark.parametrize("error,codigo", [(BonitaClientError("No disponible"), 503),
    (httpx.ReadTimeout("Respuesta perdida"), 503), (BonitaTaskConflictError("Conflicto"), 409)])
def test_falla_bonita_no_reintenta_ejecucion(evaluacion, operacion, error, codigo):
    cliente, sesiones = evaluacion
    anterior = estado(sesiones)
    getattr(bonita_client, operacion).side_effect = error
    assert decidir(cliente).status_code == codigo
    assert bonita_client.ejecutar_tarea.await_count <= 1
    assert estado(sesiones) == anterior


def test_tarea_ya_archivada_no_se_repite_aunque_lectura_ready_se_retrase(evaluacion):
    cliente, _ = evaluacion
    bonita_client.tarea_completada.return_value = True
    assert decidir(cliente).status_code == 409
    bonita_client.tarea_completada.assert_awaited_once_with(42, "101", "Evaluar proyecto")
    bonita_client.ejecutar_tarea.assert_not_awaited()


def test_segundo_envio_del_mismo_id_no_repite_la_tarea_archivada(evaluacion):
    cliente, _ = evaluacion
    bonita_client.tarea_completada.side_effect = [False, True]
    assert decidir(cliente, "CONTINUAR_PARCIAL").status_code == 202
    assert decidir(cliente, "CONTINUAR_PARCIAL").status_code == 409
    bonita_client.ejecutar_tarea.assert_awaited_once_with(101, {"accionInput": "CONTINUAR_PARCIAL"})


def test_motor_arbitra_dos_envios_mientras_su_lectura_sigue_ready(evaluacion):
    cliente, _ = evaluacion
    bonita_client.ejecutar_tarea.side_effect = [None, BonitaTaskConflictError("Tarea ya tomada")]
    assert decidir(cliente, "CONTINUAR_PARCIAL").status_code == 202
    assert decidir(cliente, "CONTINUAR_PARCIAL").status_code == 409
    assert bonita_client.ejecutar_tarea.await_count == 2


def test_continuar_parcial_conserva_compatibilidad_con_seleccion(evaluacion):
    cliente, sesiones = evaluacion
    with sesiones() as db:
        db.add(ConfirmacionSeleccion(emergencia_id=1, caso_id="42", seleccion_json="[]"))
        db.commit()
    assert decidir(cliente, "CONTINUAR_PARCIAL").status_code == 202


def test_revalida_estado_local_antes_de_ejecutar(evaluacion):
    cliente, sesiones = evaluacion

    async def consultar(caso_id, nombre):
        with sesiones() as db:
            db.get(Emergencia, 1).estado = EstadoEmergencia.EN_PROCESO
            db.commit()
        return dict(TAREA)

    bonita_client.obtener_tarea_pendiente.side_effect = consultar
    assert decidir(cliente).status_code == 409
    bonita_client.ejecutar_tarea.assert_not_awaited()


def test_caso_inexistente(evaluacion):
    cliente, _ = evaluacion
    ruta = RUTA.replace("/1/", "/999/")
    assert cliente.get(ruta, headers=cabecera(COORDINADOR)).status_code == 404
    assert cliente.post(ruta, headers=cabecera(COORDINADOR), json={"tarea_id": 101, "accion": "REABRIR"}).status_code == 404


def test_conector_aplica_una_sola_decision_despues_de_ejecutar(evaluacion):
    from app.services.curso_accion_service import CursoAccionService

    cliente, sesiones = evaluacion
    llamadas = []

    async def ejecutar(tarea_id, contrato):
        assert tarea_id == 101 and contrato == {"accionInput": "REFORMULAR"}
        with sesiones() as db:
            assert db.get(CursoAccionEmergencia, 1) is None
            llamadas.append("ON_FINISH")
            CursoAccionService().aplicar(db, 1, "REFORMULAR")
        llamadas.append("completada")

    bonita_client.ejecutar_tarea.side_effect = ejecutar
    assert decidir(cliente, "REFORMULAR").status_code == 202
    assert llamadas == ["ON_FINISH", "completada"]
    with sesiones() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.ESPERA_LOTES
        assert db.query(CursoAccionEmergencia).count() == 1
    assert decidir(cliente, "REFORMULAR").status_code == 409
    bonita_client.ejecutar_tarea.assert_awaited_once()


def test_postgresql_libera_transaccion_antes_del_callback(sesiones_pg, monkeypatch):
    import asyncio

    from sqlalchemy import select
    from app.schemas.emergencias_schema import EvaluacionProyectoEntrada
    from app.services.curso_accion_service import CursoAccionService
    from app.services.evaluacion_proyecto_service import EvaluacionProyectoService

    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        emergencia.publicada = True
        emergencia.bonita_case_id = "42"
        db.commit()
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value={**TAREA, "assigned_id": "12"}))
    monkeypatch.setattr(bonita_client, "tarea_completada", AsyncMock(return_value=False))
    with sesiones_pg() as solicitud_db:
        # Reproduce incluso un lock previo: el envío debe soltar toda la
        # transacción antes de que ON_FINISH abra una sesión independiente.
        solicitud_db.execute(select(Emergencia).where(Emergencia.id == 1).with_for_update()).scalar_one()

        async def ejecutar(tarea_id, contrato):
            assert not solicitud_db.in_transaction()
            with sesiones_pg() as callback_db:
                CursoAccionService().aplicar(callback_db, 1, contrato["accionInput"])

        envio = AsyncMock(side_effect=ejecutar)
        monkeypatch.setattr(bonita_client, "ejecutar_tarea", envio)
        respuesta = asyncio.run(EvaluacionProyectoService().ejecutar(
            solicitud_db, 1, EvaluacionProyectoEntrada(tarea_id=101, accion="REFORMULAR")))
        assert respuesta.tarea_id == 101
        envio.assert_awaited_once_with(101, {"accionInput": "REFORMULAR"})
    with sesiones_pg() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.ESPERA_LOTES
        assert db.query(CursoAccionEmergencia).count() == 1


@pytest.mark.parametrize("cambios", [{"id": "invalido"}, {"id": True},
                                    {"actorId": "invalido"}, {"assigned_id": "invalido"}])
def test_respuesta_bonita_malformada_no_ejecuta(evaluacion, cambios):
    cliente, _ = evaluacion
    bonita_client.obtener_tarea_pendiente.return_value = {**TAREA, **cambios}
    assert decidir(cliente).status_code == 503
    bonita_client.ejecutar_tarea.assert_not_awaited()
