"""Decisiones del supervisor y siguientes ciclos del mismo caso, por API."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.bonita.client import bonita_client, BonitaClientError
from app.models import CursoAccionEmergencia, ConfirmacionSeleccion, Emergencia, EstadoEmergencia, LoteNecesidad, OfertaAyuda
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno
from test_solicitud_evaluacion import crear_oferta, solicitud

RUTA = "/api/v1/emergencias/1"


@pytest.fixture
def evaluada(solicitud, monkeypatch):
    cliente, sesiones, _, _ = solicitud
    alta = crear_oferta(solicitud)
    assert alta.status_code == 201, alta.text
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.bonita_case_id = "42"
        emergencia.fecha_publicacion = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.commit()
    assert cliente.get(f"{RUTA}/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 200
    tarea = AsyncMock(return_value={"id": "101", "caseId": "42", "name": "Generar lotes",
                                   "actorId": "7", "assigned_id": "0", "state": "ready"})
    ejecutar = AsyncMock()
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", tarea)
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)
    monkeypatch.setattr(bonita_client, "tarea_completada", AsyncMock(return_value=False))
    return solicitud, tarea, ejecutar


def decidir(cliente, accion, rol=COORDINADOR):
    return cliente.post(f"{RUTA}/curso-accion", headers=cabecera(rol), json={"accion": accion})


def test_reabrir_conserva_datos_y_permite_oferta_y_segunda_evaluacion(evaluada):
    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, _ = solicitud
    for _ in range(2):
        respuesta = decidir(cliente, "REABRIR")
        assert respuesta.status_code == 204, respuesta.text
        assert respuesta.content == b""
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        assert emergencia.estado == EstadoEmergencia.ESPERA_OFERTAS
        assert emergencia.publicada and emergencia.bonita_case_id == "42"
        assert len(emergencia.lotes) == 3 and len(emergencia.ofertas) == 1
    assert crear_oferta(solicitud).status_code == 201
    assert cliente.get(f"{RUTA}/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 200
    tarea.assert_not_awaited()
    ejecutar.assert_not_awaited()


@pytest.mark.parametrize("agregar", [False, True])
def test_reformular_edita_y_publica_sin_liberar_la_barrera_antes(evaluada, agregar):
    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, lotes = solicitud
    for _ in range(2):
        assert decidir(cliente, "REFORMULAR").status_code == 204
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        assert emergencia.estado == EstadoEmergencia.ESPERA_LOTES and not emergencia.publicada
        assert emergencia.fecha_publicacion is not None and len(emergencia.ofertas) == 1
    # Las ONG no acceden a emergencias no publicadas (permiso existente).
    assert crear_oferta(solicitud).status_code == 403
    assert cliente.patch(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR),
                         json={"cantidad": 20}).status_code == 200
    if agregar:
        assert cliente.post(f"{RUTA}/lotes", headers=cabecera(COORDINADOR),
                            json={"tipo": "Agua", "cantidad": 4, "tipo_recurso_id": 41}).status_code == 201
    tarea.assert_not_awaited()
    ejecutar.assert_not_awaited()
    for _ in range(2):
        publicada = cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR))
        assert publicada.status_code == 200, publicada.text
        assert publicada.json()["publicada"] and publicada.json()["bonita_case_id"] == "42"
    ejecutar.assert_awaited_once_with("101")
    assert cliente.get(f"{RUTA}/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 200


def test_continuar_parcial_no_modifica_la_espera_de_adjudicacion(evaluada):
    solicitud, tarea, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    for _ in range(2):
        assert decidir(cliente, "CONTINUAR_PARCIAL", AUDITOR).status_code == 204
    with sesiones() as db:
        assert db.get(Emergencia, 1).estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
    tarea.assert_not_awaited()


@pytest.mark.parametrize("rol,codigo", [(ONG, 403), (OPERADOR, 403), (None, 401)])
def test_callback_usa_la_misma_autenticacion_que_solicitud_evaluacion(evaluada, rol, codigo):
    cliente = evaluada[0][0]
    respuesta = cliente.post(f"{RUTA}/curso-accion", headers=cabecera(rol) if rol else {},
                             json={"accion": "REABRIR"})
    assert respuesta.status_code == codigo


@pytest.mark.parametrize("cuerpo", [{}, {"accion": "reabrir"}, {"accion": "OTRA"},
                                    {"accion": "REABRIR", "caso_id": 42}, {"accion": None}])
def test_callback_rechaza_contratos_distintos(evaluada, cuerpo):
    cliente = evaluada[0][0]
    assert cliente.post(f"{RUTA}/curso-accion", headers=cabecera(COORDINADOR), json=cuerpo).status_code == 422


@pytest.mark.parametrize("estado", [EstadoEmergencia.RESUELTA, EstadoEmergencia.EN_PROCESO,
                                   EstadoEmergencia.ESPERA_LOTES, EstadoEmergencia.ESPERA_OFERTAS])
@pytest.mark.parametrize("accion", ["REABRIR", "REFORMULAR", "CONTINUAR_PARCIAL"])
def test_no_acepta_decisiones_fuera_de_fase(evaluada, estado, accion):
    solicitud, _, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    with sesiones() as db:
        db.get(Emergencia, 1).estado = estado
        db.commit()
    assert decidir(cliente, accion).status_code == 409


@pytest.mark.parametrize("pendiente", [False, True])
def test_no_retrocede_si_hay_seleccion_en_curso(evaluada, pendiente):
    solicitud, _, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    with sesiones() as db:
        if pendiente:
            db.add(ConfirmacionSeleccion(emergencia_id=1, caso_id="42", seleccion_json="[]"))
        else:
            db.query(OfertaAyuda).filter_by(emergencia_id=1).first().adjudicada_en = datetime.now(timezone.utc)
        db.commit()
    assert decidir(cliente, "REFORMULAR").status_code == 409
    assert decidir(cliente, "REABRIR").status_code == 409


def test_callback_inexistente_devuelve_404(evaluada):
    cliente = evaluada[0][0]
    assert cliente.post("/api/v1/emergencias/999/curso-accion", headers=cabecera(COORDINADOR),
                        json={"accion": "REABRIR"}).status_code == 404


def test_republicar_sin_tarea_no_abre_la_convocatoria(evaluada):
    solicitud, tarea, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    tarea.return_value = None
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 409
    with sesiones() as db:
        assert not db.get(Emergencia, 1).publicada


def test_republicar_reconcilia_respuesta_perdida_solo_con_tarea_exacta(evaluada, monkeypatch):
    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, _ = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    ejecutar.side_effect = httpx.ReadTimeout("Respuesta perdida")
    completada = AsyncMock(return_value=False)
    monkeypatch.setattr(bonita_client, "tarea_completada", completada, raising=False)
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 503
    with sesiones() as db:
        assert not db.get(Emergencia, 1).publicada
    tarea.return_value = None
    completada.return_value = True
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 200
    completada.assert_awaited_with(42, "101", "Generar lotes")
    ejecutar.assert_awaited_once()


def test_reformular_no_reinterpreta_ofertas_previas_como_otro_recurso(evaluada):
    solicitud, _, _ = evaluada
    cliente, _, _, lotes = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    for cambios in ({"tipo": "Abrigo"}, {"tipo_recurso_id": 73}, {"tipo_recurso_id": None}, {"unidad": "bidones"}):
        assert cliente.patch(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR),
                             json=cambios).status_code == 409


@pytest.mark.parametrize("fecha_historica", [False, True])
def test_primer_ciclo_conserva_barrera_en_alta_y_publicacion_local(entorno, monkeypatch, fecha_historica):
    cliente, sesiones, _ = entorno
    if fecha_historica:
        with sesiones() as db:
            db.get(Emergencia, 1).fecha_publicacion = datetime(2026, 1, 1, tzinfo=timezone.utc)
            db.commit()
    assert cliente.post(f"{RUTA}/bonita/iniciar", headers=cabecera(COORDINADOR)).status_code == 200
    tarea = AsyncMock(return_value={"id": "10", "caseId": "42", "name": "Generar lotes",
                                    "actorId": "7", "assigned_id": "0", "state": "ready"})
    ejecutar = AsyncMock()
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", tarea)
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)
    assert cliente.post(f"{RUTA}/lotes", headers=cabecera(COORDINADOR),
                        json={"tipo": "Agua", "cantidad": 4}).status_code == 201
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 200
    tarea.assert_awaited_once_with(42, "Generar lotes")
    ejecutar.assert_awaited_once_with("10")
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 409
    tarea.assert_awaited_once()


def test_callback_conserva_instantanea_original_del_contrato(evaluada):
    solicitud, _, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    original = '{"emergencia_id": 1, "lotes_json": "[]"}'
    with sesiones() as db:
        db.get(Emergencia, 1).bonita_variables_json = original
        db.commit()
    assert decidir(cliente, "REFORMULAR").status_code == 204
    assert cliente.get(RUTA, headers=cabecera(COORDINADOR)).json()["bonita_variables_json"] == original


def test_publicacion_incierta_congela_lotes_y_no_ejecuta_otra_ronda(evaluada):
    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, lotes = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    ejecutar.side_effect = BonitaClientError("Respuesta perdida")
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 503
    assert cliente.patch(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR),
                         json={"cantidad": 20}).status_code == 409
    assert cliente.post(f"{RUTA}/lotes", headers=cabecera(COORDINADOR),
                        json={"tipo": "Agua", "cantidad": 1}).status_code == 409
    tarea.return_value = {**tarea.return_value, "id": "102"}
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 409
    ejecutar.assert_awaited_once()
    with sesiones() as db:
        assert not db.get(Emergencia, 1).publicada
        assert db.get(CursoAccionEmergencia, 1).tarea_publicacion_id == "101"


def test_publicacion_reconcilia_commit_local_fallido(evaluada, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, _ = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    fallar = True

    def antes_commit(db):
        nonlocal fallar
        if fallar and any(isinstance(objeto, Emergencia) and objeto.publicada for objeto in db.dirty):
            fallar = False
            raise SQLAlchemyError("Commit local fallido")

    event.listen(sesiones.class_, "before_commit", antes_commit)
    try:
        assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 503
    finally:
        event.remove(sesiones.class_, "before_commit", antes_commit)
    with sesiones() as db:
        assert not db.get(Emergencia, 1).publicada
    tarea.return_value = None
    monkeypatch.setattr(bonita_client, "tarea_completada", AsyncMock(return_value=True))
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 200
    ejecutar.assert_awaited_once()


def test_cada_reformulacion_registra_su_propia_tarea(evaluada):
    solicitud, tarea, ejecutar = evaluada
    cliente, sesiones, _, _ = solicitud
    for identificador in ("101", "201"):
        assert decidir(cliente, "REFORMULAR").status_code == 204
        tarea.return_value = {**tarea.return_value, "id": identificador}
        assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 200
        with sesiones() as db:
            assert db.get(CursoAccionEmergencia, 1).tarea_publicacion_id == identificador
        assert cliente.get(f"{RUTA}/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 200
    assert ejecutar.await_count == 2


@pytest.mark.parametrize("primera,segunda", [("CONTINUAR_PARCIAL", "REABRIR"),
                                            ("CONTINUAR_PARCIAL", "REFORMULAR"),
                                            ("REABRIR", "CONTINUAR_PARCIAL"),
                                            ("REFORMULAR", "CONTINUAR_PARCIAL")])
def test_una_evaluacion_no_acepta_dos_decisiones_distintas(evaluada, primera, segunda):
    solicitud, _, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    assert decidir(cliente, primera).status_code == 204
    assert decidir(cliente, segunda).status_code == 409
    assert decidir(cliente, primera).status_code == 204
    with sesiones() as db:
        assert db.get(CursoAccionEmergencia, 1).accion == primera


def test_republicar_respeta_la_asignacion_existente_de_bonita(evaluada):
    solicitud, tarea, ejecutar = evaluada
    cliente, _, _, _ = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    tarea.return_value = {**tarea.return_value, "assigned_id": "99"}
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 200
    bonita_client.obtener_miembro_actor.assert_not_awaited()
    bonita_client.asignar_tarea.assert_not_awaited()
    ejecutar.assert_awaited_once_with("101")


def test_callback_sin_caso_no_inventa_una_instancia(evaluada):
    solicitud, tarea, _ = evaluada
    cliente, sesiones, _, _ = solicitud
    with sesiones() as db:
        db.get(Emergencia, 1).bonita_case_id = None
        db.commit()
    assert decidir(cliente, "REFORMULAR").status_code == 409
    tarea.assert_not_awaited()


def test_publicacion_incierta_congela_lotes_hasta_reconciliar(evaluada, monkeypatch):
    solicitud, _, ejecutar = evaluada
    cliente, sesiones, _, lotes = solicitud
    assert decidir(cliente, "REFORMULAR").status_code == 204
    ejecutar.side_effect = BonitaClientError("Respuesta perdida")
    assert cliente.post(f"{RUTA}/publicar", headers=cabecera(COORDINADOR)).status_code == 503
    assert cliente.patch(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR),
                         json={"cantidad": 99}).status_code == 409
    assert cliente.post(f"{RUTA}/lotes", headers=cabecera(COORDINADOR),
                        json={"tipo": "Agua", "cantidad": 4}).status_code == 409
    assert cliente.delete(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR)).status_code == 409
    with sesiones() as db:
        assert not db.get(Emergencia, 1).publicada and len(db.get(Emergencia, 1).lotes) == 3


def test_reformulacion_preserva_referencia_al_normalizar_nombre_historico(evaluada):
    solicitud, _, _ = evaluada
    cliente, sesiones, _, lotes = solicitud
    with sesiones() as db:
        db.get(LoteNecesidad, lotes[0]).tipo = "agua"
        db.commit()
    assert decidir(cliente, "REFORMULAR").status_code == 204
    respuesta = cliente.patch(f"/api/v1/lotes/{lotes[0]}", headers=cabecera(COORDINADOR), json={"tipo": "Agua"})
    assert respuesta.status_code == 200
    assert respuesta.json()["tipo_recurso_id"] == 41
