"""Avisos durables con sesiones aisladas y SMTP exclusivamente simulado."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations.email import service as correo_service
from app.integrations.email.client import EmailClientError
from app.models import (AvisoAdjudicacion, ConfirmacionSeleccion, Emergencia,
                        EstadoEmergencia, OfertaAyuda, Organizacion)
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from app.services import ofertas_service
from app.services.notificaciones_adjudicacion_service import (
    consumir_avisos, procesar_aviso_pendiente,
)
from test_confirmar_seleccion import PARES, adjudicar, confirmar, preparar_marcas, seleccion
from test_concurrencia import sesiones_pg
from test_permisos_api import cabecera, entorno, estado


RUTA_AVISO = "/api/v1/emergencias/2/notificar-adjudicacion"


def solicitar_aviso(seleccion, rol=COORDINADOR, caso_id=42):
    return seleccion[0].post(RUTA_AVISO, params={"caso_id": caso_id}, headers=cabecera(rol))


@pytest.mark.parametrize("rol", [COORDINADOR, AUDITOR])
@pytest.mark.parametrize("resuelta", [False, True])
def test_callback_encola_solo_seleccion_confirmada_sin_enviar(seleccion, rol, resuelta):
    seleccion[2]["seleccion"] = PARES
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = (EstadoEmergencia.RESUELTA if resuelta else EstadoEmergencia.EN_PROCESO)
        db.add(AvisoAdjudicacion(oferta_id=1))
        db.commit()
    respuesta = solicitar_aviso(seleccion, rol)
    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.content == b""
    seleccion[3][1].assert_not_called()
    with seleccion[1]() as db:
        assert sorted(aviso.oferta_id for aviso in db.query(AvisoAdjudicacion)) == [1, 2]
        assert all(aviso.enviada_en is None for aviso in db.query(AvisoAdjudicacion))
        assert db.get(Emergencia, 2).estado == (EstadoEmergencia.RESUELTA if resuelta else EstadoEmergencia.EN_PROCESO)


@pytest.mark.parametrize("rol", [ONG, OPERADOR])
def test_callback_rechaza_roles_sin_mutaciones(seleccion, rol):
    anterior = estado(seleccion[1])
    assert solicitar_aviso(seleccion, rol).status_code == 403
    assert estado(seleccion[1]) == anterior


@pytest.mark.parametrize("caso_id", [None, 0, -1, "invalido"])
def test_callback_exige_caso_positivo(seleccion, caso_id):
    parametros = {} if caso_id is None else {"caso_id": caso_id}
    anterior = estado(seleccion[1])
    respuesta = seleccion[0].post(RUTA_AVISO, params=parametros, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 422
    assert estado(seleccion[1]) == anterior


def test_callback_exige_sesion_y_emergencia_existente(seleccion):
    assert seleccion[0].post(RUTA_AVISO, params={"caso_id": 42}).status_code == 401
    assert seleccion[0].post(RUTA_AVISO.replace("/2/", "/999/"), params={"caso_id": 42},
                             headers=cabecera(COORDINADOR)).status_code == 404


@pytest.mark.parametrize("problema", ["otro_caso", "sin_caso", "provisional", "sin_prueba", "otra_seleccion",
                                     "exclusiva", "sin_ofertas", "bonita_caido"])
def test_callback_rechaza_caso_o_finalidad_sin_mutaciones(seleccion, problema):
    seleccion[2]["seleccion"] = PARES
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.EN_PROCESO
        if problema == "sin_caso":
            db.get(Emergencia, 2).bonita_case_id = None
        if problema == "provisional":
            db.get(Emergencia, 2).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        if problema != "exclusiva":
            db.add(AvisoAdjudicacion(oferta_id=1))
        if problema == "sin_ofertas":
            for oferta in db.query(OfertaAyuda):
                oferta.adjudicada_en = None
        db.commit()
    if problema == "sin_prueba":
        seleccion[2]["seleccion"] = []
    if problema == "otra_seleccion":
        seleccion[2]["seleccion"] = PARES[:1]
    if problema == "bonita_caido":
        seleccion[2]["caido"] = True
    anterior = estado(seleccion[1])
    respuesta = solicitar_aviso(seleccion, caso_id=43 if problema == "otro_caso" else 42)
    assert respuesta.status_code == (503 if problema == "bonita_caido" else 409), respuesta.text
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("estado_emergencia", [EstadoEmergencia.ESPERANDO_ADJUDICACION, EstadoEmergencia.ESPERA_OFERTAS,
                                             EstadoEmergencia.EN_PROCESO])
def test_callback_temprano_acepta_intencion_durable_sin_bloqueo_ni_bonita(seleccion, monkeypatch, estado_emergencia):
    from app.repositories import EmergenciaRepository

    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = estado_emergencia
        db.add(ConfirmacionSeleccion(emergencia_id=2, caso_id="42", seleccion_json=json.dumps(PARES)))
        db.commit()
    obtener = EmergenciaRepository.obtener_por_id

    def sin_bloqueo(*args, **kwargs):
        assert not kwargs.get("bloquear", False)
        return obtener(*args, **kwargs)

    monkeypatch.setattr(EmergenciaRepository, "obtener_por_id", sin_bloqueo)
    seleccion[2]["caido"] = True
    anterior = estado(seleccion[1])
    assert solicitar_aviso(seleccion).status_code == 202
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("caso,pares", [("43", PARES), ("42", PARES[:1])])
def test_callback_temprano_rechaza_intencion_de_otra_seleccion(seleccion, caso, pares):
    with seleccion[1]() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        db.add(ConfirmacionSeleccion(emergencia_id=2, caso_id=caso, seleccion_json=json.dumps(pares)))
        db.commit()
    anterior = estado(seleccion[1])
    assert solicitar_aviso(seleccion).status_code == 409
    assert estado(seleccion[1]) == anterior


@pytest.mark.parametrize("enviada", [False, True])
def test_callback_repetido_conserva_envio_intentos_y_backoff(seleccion, enviada):
    assert confirmar(seleccion).status_code == 200
    with seleccion[1]() as db:
        aviso = db.get(AvisoAdjudicacion, 1)
        aviso.intentos = 3
        aviso.proximo_intento_en = datetime.now(timezone.utc) + timedelta(hours=1)
        if enviada:
            aviso.enviada_en = datetime.now(timezone.utc)
        db.commit()
    anterior = estado(seleccion[1])
    assert solicitar_aviso(seleccion).status_code == 202
    assert solicitar_aviso(seleccion).status_code == 202
    assert estado(seleccion[1]) == anterior
    seleccion[3][1].assert_not_called()


@pytest.mark.parametrize("cambio", [None, "caso", "estado", "pares"])
def test_callback_cierra_lectura_para_bonita_y_revalida_bajo_lock(seleccion, monkeypatch, cambio):
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    assert confirmar(seleccion).status_code == 200
    sesion_lectura = []
    verificar = SeleccionOfertasService._verificar_cola_seleccion

    def recordar_sesion(db, pares):
        sesion_lectura.append(db)
        verificar(db, pares)

    async def comprobar_prueba(self, caso_id, pares):
        assert caso_id == 42
        assert pares == {(1, 2), (2, 2)}
        assert not sesion_lectura[0].in_transaction()
        with seleccion[1]() as db:
            if cambio == "caso":
                db.get(Emergencia, 2).bonita_case_id = "43"
            elif cambio == "estado":
                db.get(Emergencia, 2).estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
            elif cambio == "pares":
                db.get(OfertaAyuda, 2).adjudicada_en = None
            db.commit()
        return True

    monkeypatch.setattr(SeleccionOfertasService, "_verificar_cola_seleccion", staticmethod(recordar_sesion))
    monkeypatch.setattr(SeleccionOfertasService, "_ya_confirmada", comprobar_prueba)
    with seleccion[1]() as db:
        db.delete(db.get(AvisoAdjudicacion, 2))
        db.commit()
    respuesta = solicitar_aviso(seleccion)
    assert respuesta.status_code == (202 if cambio is None else 409), respuesta.text
    with seleccion[1]() as db:
        assert db.query(AvisoAdjudicacion).count() == (2 if cambio is None else 1)


@pytest.mark.parametrize("exclusiva", [False, True])
def test_callback_on_enter_postgresql_no_espera_al_confirmador(sesiones_pg, monkeypatch, exclusiva):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.integrations.bonita.client import bonita_client
    from app.main import app
    from app.models import OfertaItem, Rol, Usuario
    from app.services.seleccion_ofertas_service import SeleccionOfertasService

    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.bonita_case_id = "42"
        emergencia.estado = EstadoEmergencia.EN_PROCESO if exclusiva else EstadoEmergencia.ESPERANDO_ADJUDICACION
        oferta = db.get(OfertaAyuda, 1)
        oferta.adjudicada_en = datetime.now(timezone.utc)
        oferta.items = [OfertaItem(lote_necesidad_id=1, cantidad_ofrecida=3)]
        db.add(Rol(id=2, nombre=COORDINADOR))
        db.flush()
        db.add(Usuario(id=2, email="callback@example.org", nombre="Callback", apellido="Prueba",
                       password_hash="sin-login", rol_id=2))
        db.commit()

    def obtener_db():
        with sesiones_pg() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, obtener_db)
    cliente = TestClient(app)
    guardada = []
    ruta = RUTA_AVISO.replace("/2/", "/1/")
    correo = Mock()
    monkeypatch.setattr(ofertas_service, "notificar_adjudicacion", correo)

    async def variable(caso_id, nombre):
        assert caso_id == 42
        return json.dumps(guardada if nombre == "seleccionOfertasJson" else {
            "emergencia_id": 1, "resultados": [
                {"oferta_id": 1, "lote_id": 1, "cantidad_verificada": 3}]})

    async def ejecutar(tarea_id, contrato):
        # El confirmador conserva el lock hasta que este callback HTTP retorna.
        respuesta = await asyncio.wait_for(asyncio.to_thread(
            cliente.post, ruta, params={"caso_id": 42}, headers=cabecera(COORDINADOR)), timeout=2)
        assert respuesta.status_code == 202, respuesta.text
        assert respuesta.content == b""
        with sesiones_pg() as db:
            assert db.get(ConfirmacionSeleccion, 1) is not None
            assert db.query(AvisoAdjudicacion).count() == 0
        guardada.extend(contrato["seleccionInput"])

    monkeypatch.setattr(bonita_client, "obtener_variable_caso", variable)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value={
        "id": "99", "caseId": "42", "name": "Seleccionar oferta", "actorId": "7", "assigned_id": "12"}))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    ejecucion = AsyncMock(side_effect=ejecutar)
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecucion)
    with sesiones_pg() as db:
        assert asyncio.run(SeleccionOfertasService().confirmar(db, 1)).cantidad_pares == 1
    ejecucion.assert_awaited_once()
    correo.assert_not_called()
    with sesiones_pg() as db:
        assert db.get(ConfirmacionSeleccion, 1) is None
        assert db.query(AvisoAdjudicacion).count() == (0 if exclusiva else 1)
    respuesta = cliente.post(ruta, params={"caso_id": 42}, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == (409 if exclusiva else 202), respuesta.text
    cliente.close()


def preparar_aviso(seleccion, oferta_id=1):
    preparar_marcas(seleccion)
    assert adjudicar(seleccion, oferta_id, True).status_code == 200
    assert confirmar(seleccion).status_code == 200
    seleccion[3][1].assert_not_called()


def correo_simulado(monkeypatch, *, configurado=True, enviar=None):
    cliente = SimpleNamespace(configurado=configurado, enviar=enviar or Mock())
    monkeypatch.setattr(correo_service, "email_client", cliente)
    monkeypatch.setattr(ofertas_service, "notificar_adjudicacion", correo_service.notificar_adjudicacion)
    return cliente


def habilitar_reintento(sesiones):
    with sesiones() as db:
        for aviso in db.query(AvisoAdjudicacion):
            aviso.proximo_intento_en = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def test_smtp_fallido_persiste_backoff_y_reintenta_sin_duplicar(seleccion, monkeypatch):
    preparar_aviso(seleccion)
    enviar = Mock(side_effect=[EmailClientError("Fallo simulado"), None])
    correo_simulado(monkeypatch, enviar=enviar)
    sesiones = seleccion[1]
    assert procesar_aviso_pendiente(sesiones) is True
    with sesiones() as db:
        aviso = db.get(AvisoAdjudicacion, 1)
        creada_en = aviso.creada_en
        assert aviso.enviada_en is None and aviso.intentos == 1
        assert aviso.proximo_intento_en > datetime.now(timezone.utc).replace(tzinfo=None)
    assert procesar_aviso_pendiente(sesiones) is False
    assert confirmar(seleccion).json()["ya_confirmada"] is True
    habilitar_reintento(sesiones)
    assert procesar_aviso_pendiente(sesiones) is True
    assert procesar_aviso_pendiente(sesiones) is False
    assert enviar.call_count == 2
    assert f"Fecha y hora de adjudicacion: {creada_en}" in enviar.call_args.args[2]
    with sesiones() as db:
        assert db.query(AvisoAdjudicacion).count() == 1
        aviso = db.get(AvisoAdjudicacion, 1)
        assert aviso.enviada_en is not None and aviso.intentos == 2
        assert aviso.creada_en == creada_en


@pytest.mark.parametrize("falta", ["smtp", "destinatarios"])
def test_aviso_sin_smtp_o_destinatarios_permanece_recuperable(seleccion, monkeypatch, falta):
    preparar_aviso(seleccion, oferta_id=2 if falta == "destinatarios" else 1)
    cliente = correo_simulado(monkeypatch, configurado=falta != "smtp")
    sesiones = seleccion[1]
    assert procesar_aviso_pendiente(sesiones) is True
    cliente.enviar.assert_not_called()
    with sesiones() as db:
        aviso = db.query(AvisoAdjudicacion).one()
        assert aviso.enviada_en is None and aviso.intentos == 1
        if falta == "destinatarios":
            db.get(Organizacion, 2).email = "contacto@example.org"
            db.commit()
    cliente.configurado = True
    habilitar_reintento(sesiones)
    assert procesar_aviso_pendiente(sesiones) is True
    cliente.enviar.assert_called_once()
    with sesiones() as db:
        assert db.query(AvisoAdjudicacion).one().enviada_en is not None


def test_envio_tolerante_exclusivo_conserva_comportamiento(monkeypatch):
    enviar = Mock(side_effect=EmailClientError("Fallo simulado"))
    cliente = correo_simulado(monkeypatch, enviar=enviar)
    argumentos = (["contacto@example.org"], 1, 2, "Zona", ["Agua"], datetime.now(timezone.utc))
    correo_service.notificar_adjudicacion(*argumentos)
    enviar.assert_called_once()
    with pytest.raises(EmailClientError):
        correo_service.notificar_adjudicacion(*argumentos, estricto=True)
    cliente.configurado = False
    correo_service.notificar_adjudicacion(*argumentos)
    correo_service.notificar_adjudicacion([], *argumentos[1:])
    assert enviar.call_count == 2


def test_dos_consumidores_postgresql_no_envian_el_mismo_aviso(sesiones_pg, monkeypatch):
    with sesiones_pg() as db:
        db.get(OfertaAyuda, 1).adjudicada_en = datetime.now(timezone.utc)
        db.add(AvisoAdjudicacion(oferta_id=1))
        db.commit()
    entro_smtp, liberar_smtp = Event(), Event()

    def enviar(*args, **kwargs):
        assert kwargs == {"estricto": True}
        entro_smtp.set()
        assert liberar_smtp.wait(5)

    envio = Mock(side_effect=enviar)
    monkeypatch.setattr(ofertas_service, "notificar_adjudicacion", envio)
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        primero = ejecutor.submit(procesar_aviso_pendiente, sesiones_pg)
        try:
            assert entro_smtp.wait(5)
            segundo = ejecutor.submit(procesar_aviso_pendiente, sesiones_pg)
            assert segundo.result(timeout=2) is False
        finally:
            liberar_smtp.set()
        assert primero.result(timeout=5) is True
    assert procesar_aviso_pendiente(sesiones_pg) is False
    envio.assert_called_once()
    with sesiones_pg() as db:
        aviso = db.get(AvisoAdjudicacion, 1)
        assert aviso.intentos == 1 and aviso.enviada_en is not None


def test_despachador_usa_reloj_de_base_para_vencimiento_y_backoff(seleccion, monkeypatch):
    from app.services import notificaciones_adjudicacion_service as despachador
    from sqlalchemy import func, select

    preparar_aviso(seleccion)
    sesiones = seleccion[1]
    with sesiones() as db:
        ahora_base = db.scalar(select(func.now()))
        db.get(AvisoAdjudicacion, 1).proximo_intento_en = ahora_base - timedelta(seconds=1)
        db.commit()
    reloj_atrasado = datetime.now(timezone.utc) - timedelta(days=1)
    monkeypatch.setattr(despachador, "datetime", SimpleNamespace(now=lambda _: reloj_atrasado),
                        raising=False)
    correo_simulado(monkeypatch, enviar=Mock(side_effect=EmailClientError("Fallo simulado")))
    assert procesar_aviso_pendiente(sesiones) is True
    with sesiones() as db:
        aviso = db.get(AvisoAdjudicacion, 1)
        assert aviso.intentos == 1 and aviso.enviada_en is None
        assert aviso.proximo_intento_en >= ahora_base + timedelta(seconds=30)
    assert procesar_aviso_pendiente(sesiones) is False


def test_consumidor_consulta_al_arrancar_y_periodicamente_fuera_del_event_loop(monkeypatch):
    hilos = []
    esperas = []
    hilo_principal = get_ident()

    async def ejecutar():
        detener = asyncio.Event()
        fabrica = object()

        def procesar(sesiones):
            assert sesiones is fabrica
            hilos.append(get_ident())
            return False

        esperar = asyncio.wait_for

        async def espera_breve(tarea, *, timeout):
            esperas.append(timeout)
            if len(esperas) == 2:
                detener.set()
            return await esperar(tarea, timeout=0.001)

        monkeypatch.setattr("app.services.notificaciones_adjudicacion_service.procesar_aviso_pendiente", procesar)
        monkeypatch.setattr(asyncio, "wait_for", espera_breve)
        await consumir_avisos(detener, fabrica)

    asyncio.run(ejecutar())
    assert len(hilos) == 2 and all(hilo != hilo_principal for hilo in hilos)
    assert esperas == [5, 5]


def test_lifespan_inicia_consumidor_y_espera_su_cierre(monkeypatch):
    from app import main

    fabrica = Mock()
    monkeypatch.setattr(main, "SessionLocal", fabrica)
    monkeypatch.setattr(main.rol_service, "sembrar_roles", Mock())
    monkeypatch.setattr(main.auth_service, "sembrar_usuarios_iniciales", Mock())
    monkeypatch.setattr(main, "sembrar_datos_demo", Mock())

    async def ejecutar():
        iniciado, terminado = asyncio.Event(), asyncio.Event()

        async def consumir(detener, sesiones):
            assert sesiones is fabrica
            iniciado.set()
            await detener.wait()
            terminado.set()

        monkeypatch.setattr(main, "consumir_avisos", consumir)
        async with main.lifespan(main.app):
            await asyncio.wait_for(iniciado.wait(), timeout=1)
            assert not terminado.is_set()
        assert terminado.is_set()
        fabrica.return_value.close.assert_called_once()

    asyncio.run(ejecutar())
