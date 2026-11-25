"""Contrato mínimo para finalizar una oferta adjudicada en Bonita."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.integrations.bonita.client import bonita_client
from app.models import Emergencia, OfertaAyuda, OfertaItem
from app.services.permisos_service import COORDINADOR, ONG
from test_permisos_api import cabecera, entorno


def preparar_oferta(sesiones, *, adjudicada=True, finalizada=True, caso="42"):
    with sesiones() as db:
        emergencia = db.get(Emergencia, 2)
        emergencia.bonita_case_id = caso
        oferta = db.get(OfertaAyuda, 1)
        oferta.adjudicada_en = datetime.now(timezone.utc) if adjudicada else None
        for item in oferta.items:
            item.finalizado_en = datetime.now(timezone.utc) if finalizada else None
        db.commit()


def tarea_finalizacion():
    return {
        "id": "99",
        "caseId": "42",
        "name": "Marcar actividades finalizadas",
        "actorId": "7",
    }


def test_finalizar_oferta_solo_continua_con_confirmacion_de_bonita(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones)
    tarea = {"id": "100", "caseId": "42", "name": "Supervisar proyecto", "actorId": "8"}
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", AsyncMock(return_value=True))
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=tarea))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    monkeypatch.setattr(bonita_client, "asignar_tarea", AsyncMock())
    ejecutar = AsyncMock()
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)

    respuesta = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "oferta_id": 1, "estado": "finalizada", "ya_finalizada": True,
        "tarea_bonita": "Supervisar proyecto",
        "mensaje": "Bonita ejecutó 'Supervisar proyecto' y continuará con 'Liberación de recursos'",
    }
    ejecutar.assert_awaited_once_with("100")


def test_finalizar_oferta_responde_409_hasta_confirmacion_de_bonita(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=None))
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", AsyncMock(return_value=False))

    respuesta = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["habilitada"] is False
    assert respuesta.json()["detail"]["tarea"] == "Supervisar proyecto"


def test_finalizar_oferta_rechaza_item_pendiente(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones, finalizada=False)
    consulta = AsyncMock()
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", consulta)

    respuesta = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "codigo": "TAREA_NO_HABILITADA",
        "habilitada": False,
        "tarea": "Supervisar proyecto",
        "mensaje": (
            "La tarea 'Supervisar proyecto' aún no está habilitada: "
            "todos los ítems de la oferta adjudicada deben estar finalizados"
        ),
    }
    consulta.assert_not_awaited()


def test_ultimo_item_ejecuta_tarea_de_finalizacion_de_la_ong(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones, finalizada=False)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=tarea_finalizacion()))
    monkeypatch.setattr(bonita_client, "obtener_miembro_actor", AsyncMock(return_value={"user_id": "12"}))
    asignar = AsyncMock()
    ejecutar = AsyncMock()
    monkeypatch.setattr(bonita_client, "asignar_tarea", asignar)
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)

    respuesta = cliente.post(
        "/api/v1/ofertas/1/items/1/finalizar", headers=cabecera(ONG)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["finalizado_en"]
    asignar.assert_awaited_once_with("99", 12)
    ejecutar.assert_awaited_once_with("99")


def test_ultimo_item_tolera_tarea_ong_aun_no_disponible(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones, finalizada=False)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=None))
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", AsyncMock(return_value=False))

    respuesta = cliente.post(
        "/api/v1/ofertas/1/items/1/finalizar", headers=cabecera(ONG)
    )

    assert respuesta.status_code == 200, respuesta.text


def test_cierre_coordinador_idempotente_si_supervisar_ya_esta_completada(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones)
    monkeypatch.setattr(bonita_client, "obtener_tarea_pendiente", AsyncMock(return_value=None))
    completada = AsyncMock(side_effect=[True, True])
    monkeypatch.setattr(bonita_client, "tarea_completada_por_nombre", completada)
    ejecutar = AsyncMock()
    monkeypatch.setattr(bonita_client, "ejecutar_tarea", ejecutar)

    respuesta = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(COORDINADOR))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ya_finalizada"] is True
    ejecutar.assert_not_awaited()


@pytest.mark.parametrize("rol", [ONG])
def test_finalizar_oferta_restringida_a_coordinador(entorno, rol):
    cliente, sesiones, _ = entorno
    preparar_oferta(sesiones)

    respuesta = cliente.post("/api/v1/ofertas/1/finalizar", headers=cabecera(rol))

    assert respuesta.status_code == 403
