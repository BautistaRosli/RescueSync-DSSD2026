"""Bandejas del coordinador por etapa real, sin modificar los casos."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.integrations.bonita.client import BonitaClientError, bonita_client
from app.models import Emergencia, EstadoEmergencia
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import EMERGENCIA, cabecera, entorno, estado
from test_concurrencia import sesiones_pg

RUTA = "/api/v1/emergencias/bandeja"


@pytest.fixture
def bandejas(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    ahora = datetime.now(timezone.utc)
    with sesiones() as db:
        for identificador in range(1, 9):
            emergencia = db.get(Emergencia, identificador)
            if emergencia is None:
                emergencia = Emergencia(id=identificador, **EMERGENCIA)
                db.add(emergencia)
            emergencia.publicada = True
            emergencia.estado = (EstadoEmergencia.ESPERA_OFERTAS if identificador <= 3
                                  else EstadoEmergencia.ESPERANDO_ADJUDICACION)
            emergencia.bonita_case_id = str(40 + identificador)
            emergencia.fecha_hora_registro = ahora + timedelta(seconds=identificador)
        db.get(Emergencia, 7).estado = EstadoEmergencia.EN_PROCESO
        db.get(Emergencia, 8).bonita_case_id = None
        db.commit()
    monkeypatch.setattr(bonita_client, "obtener_casos_con_ofertas_abiertas", AsyncMock(return_value={"41", "43"}), raising=False)
    monkeypatch.setattr(bonita_client, "obtener_casos_con_tarea_lista", AsyncMock(
        side_effect=lambda nombre: {"44", "47"} if nombre == "Evaluar proyecto" else {"45", "47"}), raising=False)
    return cliente, sesiones


@pytest.mark.parametrize("etapa,ids", [("esperando_ofertas", [3, 1]),
                                      ("esperando_evaluacion", [4]),
                                      ("esperando_adjudicacion", [5])])
def test_etapa_real_filtra_antes_de_contar_y_paginar_sin_exigir_ofertas(bandejas, etapa, ids):
    cliente, sesiones = bandejas
    anterior = estado(sesiones)
    for pagina, identificador in enumerate(ids, 1):
        respuesta = cliente.get(RUTA, params={"publicada": True, "etapa_bonita": etapa,
                                              "por_pagina": 1, "pagina": pagina}, headers=cabecera(COORDINADOR))
        assert respuesta.status_code == 200, respuesta.text
        datos = respuesta.json()
        assert datos["total"] == len(ids) and datos["paginas"] == len(ids)
        assert [item["id"] for item in datos["items"]] == [identificador]
    assert estado(sesiones) == anterior


def test_timer_solo_consulta_casos_de_convocatoria_y_excluye_vencidos(bandejas):
    cliente, _ = bandejas
    assert cliente.get(RUTA, params={"publicada": True, "etapa_bonita": "esperando_ofertas"},
                       headers=cabecera(COORDINADOR)).status_code == 200
    bonita_client.obtener_casos_con_ofertas_abiertas.assert_awaited_once_with({"41", "42", "43"})
    bonita_client.obtener_casos_con_tarea_lista.assert_not_awaited()


@pytest.mark.parametrize("etapa", ["esperando_evaluacion", "esperando_adjudicacion"])
def test_transicion_automatica_no_es_una_tarea_lista(bandejas, etapa):
    cliente, _ = bandejas
    bonita_client.obtener_casos_con_tarea_lista.side_effect = None
    bonita_client.obtener_casos_con_tarea_lista.return_value = set()
    respuesta = cliente.get(RUTA, params={"publicada": True, "etapa_bonita": etapa}, headers=cabecera(COORDINADOR))
    assert respuesta.json()["total"] == 0 and respuesta.json()["items"] == []


def test_evaluacion_aun_lista_no_se_adelanta_a_seleccion(bandejas):
    cliente, _ = bandejas
    bonita_client.obtener_casos_con_tarea_lista.side_effect = lambda nombre: {"44"}
    respuesta = cliente.get(RUTA, params={"publicada": True, "etapa_bonita": "esperando_adjudicacion"},
                            headers=cabecera(COORDINADOR))
    assert respuesta.json()["items"] == []


@pytest.mark.parametrize("rol", [OPERADOR, ONG, AUDITOR])
def test_etapas_solo_coordinador(bandejas, rol):
    cliente, _ = bandejas
    respuesta = cliente.get(RUTA, params={"publicada": True, "etapa_bonita": "esperando_ofertas"}, headers=cabecera(rol))
    assert respuesta.status_code == 403
    bonita_client.obtener_casos_con_ofertas_abiertas.assert_not_awaited()
    bonita_client.obtener_casos_con_tarea_lista.assert_not_awaited()


@pytest.mark.parametrize("parametros", [
    {"publicada": False, "etapa_bonita": "esperando_ofertas"},
    {"publicada": True, "etapa_bonita": "desconocida"},
    {"publicada": True, "etapa_bonita": "esperando_evaluacion", "estado": "esperando_ofertas"},
])
def test_contratos_incompatibles_rechazados(bandejas, parametros):
    respuesta = bandejas[0].get(RUTA, params=parametros, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 422


@pytest.mark.parametrize("etapa", ["esperando_ofertas", "esperando_evaluacion", "esperando_adjudicacion"])
def test_error_bonita_es_503_no_una_bandeja_vacia(bandejas, etapa):
    cliente, _ = bandejas
    bonita_client.obtener_casos_con_ofertas_abiertas.side_effect = BonitaClientError("No disponible")
    bonita_client.obtener_casos_con_tarea_lista.side_effect = BonitaClientError("No disponible")
    respuesta = cliente.get(RUTA, params={"publicada": True, "etapa_bonita": etapa}, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503


def test_legacy_no_consulta_bonita_y_acepta_estado_coherente_en_opt_in(bandejas):
    cliente, _ = bandejas
    respuesta = cliente.get(RUTA, params={"publicada": True, "estado": "esperando_adjudicacion"}, headers=cabecera(AUDITOR))
    assert respuesta.status_code == 200 and respuesta.json()["total"] == 4
    bonita_client.obtener_casos_con_tarea_lista.assert_not_awaited()
    respuesta = cliente.get(RUTA, params={"publicada": True, "estado": "esperando_adjudicacion",
                                          "etapa_bonita": "esperando_evaluacion"}, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200 and respuesta.json()["total"] == 1


def test_postgresql_filtra_etapa_antes_del_conteo_y_offset(sesiones_pg, monkeypatch):
    import asyncio

    from app.services.emergencias_service import EmergenciaService

    with sesiones_pg() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.estado = EstadoEmergencia.ESPERANDO_ADJUDICACION
        emergencia.publicada = True
        emergencia.bonita_case_id = "41"
        for identificador in (2, 3):
            db.add(Emergencia(id=identificador, **EMERGENCIA, publicada=True,
                              estado=EstadoEmergencia.ESPERANDO_ADJUDICACION,
                              bonita_case_id=str(40 + identificador),
                              fecha_hora_registro=datetime.now(timezone.utc) + timedelta(days=identificador)))
        db.commit()
    monkeypatch.setattr(bonita_client, "obtener_casos_con_tarea_lista", AsyncMock(return_value={"41", "43"}))
    with sesiones_pg() as db:
        resultado = asyncio.run(EmergenciaService().listar_bandeja_por_etapa(db, "esperando_evaluacion", 2, 1))
        assert resultado.total == 2 and resultado.paginas == 2
        assert [item.id for item in resultado.items] == [1]
