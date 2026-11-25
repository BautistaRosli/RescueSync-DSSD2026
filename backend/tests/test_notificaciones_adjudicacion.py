"""Avisos durables con sesiones aisladas y SMTP exclusivamente simulado."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.integrations.email import service as correo_service
from app.integrations.email.client import EmailClientError
from app.models import AvisoAdjudicacion, OfertaAyuda, Organizacion
from app.services import ofertas_service
from app.services.notificaciones_adjudicacion_service import (
    consumir_avisos, procesar_aviso_pendiente,
)
from test_confirmar_seleccion import adjudicar, confirmar, preparar_marcas, seleccion
from test_concurrencia import sesiones_pg
from test_permisos_api import entorno


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
