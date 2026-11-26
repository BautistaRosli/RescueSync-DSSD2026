"""El cierre de Bonita pertenece a todas las ofertas adjudicadas del caso."""

import asyncio
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import AsyncMock

import pytest

from app.integrations.bonita.client import BonitaClientError, bonita_client
from app.models import Emergencia, OfertaAyuda, OfertaItem
from app.services.ofertas_service import OfertaService
from app.services.permisos_service import AUDITOR, COORDINADOR
from test_concurrencia import sesiones_pg
from test_finalizar_oferta import preparar_oferta, tarea_finalizacion
from test_permisos_api import cabecera, entorno


MENSAJE_PENDIENTES = (
    "Todavía hay otras ofertas adjudicadas con ítems pendientes de finalización"
)


@pytest.fixture
def cierre(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones, finalizada=False)
    with sesiones() as db:
        db.get(OfertaAyuda, 2).adjudicada_en = datetime.now(timezone.utc)
        db.add(OfertaItem(id=2, oferta_id=2, lote_necesidad_id=2, cantidad_ofrecida=3))
        db.commit()
    completadas = set()

    async def pendiente(caso_id, nombre):
        assert caso_id == 42
        if nombre in completadas:
            return None
        if nombre == "Marcar actividades finalizadas":
            return tarea_finalizacion()
        return {"id": "100", "caseId": "42", "name": nombre, "assigned_id": "12"}

    async def ejecutar(tarea_id):
        nombre = "Marcar actividades finalizadas" if tarea_id == "99" else "Supervisar proyecto"
        completadas.add(nombre)

    consulta = AsyncMock(side_effect=pendiente)
    ejecucion = AsyncMock(side_effect=ejecutar)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", consulta)
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", AsyncMock(
        side_effect=lambda caso, nombre: nombre in completadas))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecucion)
    return cliente, sesiones, consulta, ejecucion


def finalizar_item(cliente, oferta_id):
    return cliente.post(
        f"/api/v1/ofertas/{oferta_id}/items/{oferta_id}/finalizar",
        headers=cabecera(AUDITOR),
    )


def test_cierre_espera_todas_las_adjudicadas_y_reintenta_sin_repetir(cierre):
    cliente, sesiones, consulta, ejecutar = cierre
    primera = finalizar_item(cliente, 1)
    assert primera.status_code == 200, primera.text
    assert primera.json()["finalizado_en"]
    ejecutar.assert_not_awaited()
    consulta.assert_not_awaited()

    estado = cliente.get("/api/v1/ofertas/1/finalizacion", headers=cabecera(COORDINADOR))
    assert estado.status_code == 200, estado.text
    assert estado.json() == {
        "oferta_id": 1, "items_finalizados": True, "tarea_ong_completada": False,
        "supervisar_proyecto_pendiente": False, "habilitada": False,
        "mensaje": MENSAJE_PENDIENTES,
    }
    cierre_anticipado = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR))
    assert cierre_anticipado.status_code == 409, cierre_anticipado.text
    assert cierre_anticipado.json()["detail"] == {
        "codigo": "TAREA_NO_HABILITADA", "habilitada": False,
        "tarea": "Supervisar proyecto", "mensaje": MENSAJE_PENDIENTES,
    }
    consulta.assert_not_awaited()
    with sesiones() as db:
        assert db.get(OfertaItem, 1).finalizado_en is not None
        assert db.get(OfertaItem, 2).finalizado_en is None

    ultima = finalizar_item(cliente, 2)
    assert ultima.status_code == 200, ultima.text
    ejecutar.assert_awaited_once_with("99")
    assert finalizar_item(cliente, 1).json()["finalizado_en"] == primera.json()["finalizado_en"]
    ejecutar.assert_awaited_once_with("99")
    habilitada = cliente.get("/api/v1/ofertas/1/finalizacion", headers=cabecera(COORDINADOR))
    assert habilitada.status_code == 200, habilitada.text
    assert habilitada.json()["habilitada"] is True
    for oferta_id in (1, 2):
        respuesta = cliente.post(f"/api/v1/ofertas/{oferta_id}/finalizar", headers=cabecera(COORDINADOR))
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["ya_finalizada"] is True
    assert [llamada.args for llamada in ejecutar.await_args_list] == [("99",), ("100",)]


@pytest.mark.parametrize("sin_items", [False, True])
def test_otras_adjudicadas_pendientes_no_se_ocultan_con_no_adjudicadas_finalizadas(cierre, sin_items):
    cliente, sesiones, consulta, ejecutar = cierre
    with sesiones() as db:
        if sin_items:
            db.delete(db.get(OfertaItem, 2))
        oferta = OfertaAyuda(id=3, emergencia_id=2, organizacion_id=1)
        oferta.items = [OfertaItem(lote_necesidad_id=2, cantidad_ofrecida=1,
                                  finalizado_en=datetime.now(timezone.utc))]
        db.add(oferta)
        db.commit()
    respuesta = finalizar_item(cliente, 1)
    assert respuesta.status_code == 200, respuesta.text
    estado = cliente.get("/api/v1/ofertas/1/finalizacion", headers=cabecera(COORDINADOR))
    assert estado.json()["items_finalizados"] is True
    assert estado.json()["habilitada"] is False
    assert estado.json()["mensaje"] == MENSAJE_PENDIENTES
    assert cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR)).status_code == 409
    ejecutar.assert_not_awaited()
    consulta.assert_not_awaited()


@pytest.mark.parametrize("finalizar_no_adjudicada", [False, True])
def test_no_adjudicadas_y_otras_emergencias_no_bloquean_ni_disparan(cierre, finalizar_no_adjudicada):
    cliente, sesiones, consulta, ejecutar = cierre
    with sesiones() as db:
        db.get(OfertaAyuda, 2).adjudicada_en = None
        db.add(OfertaAyuda(id=3, emergencia_id=1, organizacion_id=1,
                          adjudicada_en=datetime.now(timezone.utc)))
        db.commit()
    if finalizar_no_adjudicada:
        assert finalizar_item(cliente, 2).status_code == 200
    consulta.assert_not_awaited()
    assert finalizar_item(cliente, 1).status_code == 200
    ejecutar.assert_awaited_once_with("99")
    assert cliente.get("/api/v1/ofertas/1/finalizacion", headers=cabecera(COORDINADOR)).json()["habilitada"] is True
    assert cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR)).status_code == 200


def test_fallo_bonita_conserva_ultimo_item_y_permite_reintentar(cierre, monkeypatch):
    cliente, sesiones, _, ejecutar = cierre
    assert finalizar_item(cliente, 1).status_code == 200
    consulta = bonita_client.obtener_tarea_pendiente
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(side_effect=BonitaClientError("Caída simulada")))
    respuesta = finalizar_item(cliente, 2)
    assert respuesta.status_code == 503, respuesta.text
    with sesiones() as db:
        fechas = [db.get(OfertaItem, item_id).finalizado_en for item_id in (1, 2)]
        assert all(fechas)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", consulta)
    assert finalizar_item(cliente, 2).status_code == 200
    ejecutar.assert_awaited_once_with("99")
    with sesiones() as db:
        assert [db.get(OfertaItem, item_id).finalizado_en for item_id in (1, 2)] == fechas


def test_no_adjudicada_devuelve_item_guardado_ante_edicion_tras_commit(cierre, monkeypatch):
    from app.api.routes.ofertas_api import servicio_ofertas

    cliente, sesiones, consulta, ejecutar = cierre
    with sesiones() as db:
        db.get(OfertaAyuda, 2).adjudicada_en = None
        db.commit()
    actualizar = servicio_ofertas._repository.actualizar

    def guardar_y_editar(db, oferta):
        resultado = actualizar(db, oferta)
        # Otra edición legítima retira el ítem después de guardar su cierre.
        with sesiones() as editora:
            editora.delete(editora.get(OfertaItem, 2))
            editora.commit()
        return resultado

    monkeypatch.setattr(servicio_ofertas._repository, "actualizar", guardar_y_editar)
    respuesta = finalizar_item(cliente, 2)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["id"] == 2
    assert respuesta.json()["finalizado_en"]
    consulta.assert_not_awaited()
    ejecutar.assert_not_awaited()


def test_postgresql_ultimos_items_superpuestos_ejecutan_tarea_una_vez(sesiones_pg, monkeypatch):
    with sesiones_pg() as db:
        db.get(Emergencia, 1).bonita_case_id = "42"
        db.get(OfertaAyuda, 1).adjudicada_en = datetime.now(timezone.utc)
        db.add(OfertaAyuda(id=2, emergencia_id=1, organizacion_id=1,
                          adjudicada_en=datetime.now(timezone.utc)))
        db.flush()
        db.add_all([OfertaItem(id=i, oferta_id=i, lote_necesidad_id=i, cantidad_ofrecida=1)
                    for i in (1, 2)])
        db.commit()
    servicio = OfertaService()
    actualizar = servicio._repository.actualizar
    comprometidos = Barrier(2, timeout=5)

    def guardar(db, oferta):
        resultado = actualizar(db, oferta)
        comprometidos.wait()
        return resultado

    monkeypatch.setattr(servicio._repository, "actualizar", guardar)
    completada = False

    async def pendiente(caso, nombre):
        return None if completada else tarea_finalizacion()

    async def ejecutar(_):
        nonlocal completada
        # El segundo cierre espera el bloqueo sin detener el bucle del primero.
        await asyncio.sleep(0.1)
        completada = True

    ejecucion = AsyncMock(side_effect=ejecutar)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(side_effect=pendiente))
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", AsyncMock(side_effect=lambda *_: completada))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecucion)

    async def cerrar():
        with sesiones_pg() as primera, sesiones_pg() as segunda:
            return await asyncio.wait_for(asyncio.gather(
                servicio.finalizar_item(primera, 1, 1),
                servicio.finalizar_item(segunda, 2, 2),
            ), timeout=10)

    assert all(item.finalizado_en for item in asyncio.run(cerrar()))
    ejecucion.assert_awaited_once_with("99")
