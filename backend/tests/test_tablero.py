"""Tablero del Auditor: cifras cruzadas entre RescueSync, Cloud y Bonita."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.reportes_api import FiltrosReporte
from app.database import Base
from app.integrations.bonita.client import BonitaClientError
from app.models import (
    AporteOfertaItem, AvisoAdjudicacion, CierreEmergencia, Emergencia, EstadoEmergencia,
    EvaluacionCloud, LoteNecesidad, LoteRecursoCloud, OfertaAyuda, OfertaItem, Organizacion,
    RegistroRecursos,
)
from app.repositories import EmergenciaRepository
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from app.services.tablero_service import TableroService

from test_permisos_api import cabecera, entorno  # noqa: F401

BONITA = "app.services.tablero_service.bonita_client.obtener_metricas_casos"
F = datetime


def metricas_bonita():
    return {
        "casos": {
            "10": {"estado": "completed", "inicio": F(2026, 10, 1, 10), "fin": F(2026, 10, 3, 9)},
            "20": {"estado": "activo", "inicio": F(2026, 10, 5), "fin": None},
            "30": {"estado": "completed", "inicio": F(2026, 10, 10), "fin": F(2026, 10, 11)},
            "50": {"estado": "cancelado", "inicio": F(2026, 10, 20, 23), "fin": F(2026, 10, 21)},
        },
        "tiempos_por_etapa": [{"etapa": "Generar lotes", "promedio_horas": 2.0, "cantidad": 3},
                              {"etapa": "Publicar pedido", "promedio_horas": 0.0, "cantidad": 0}],
        "casos_camino_alternativo": 1,
    }


@pytest.fixture
def db():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as sesion:
        cargar_escenario(sesion)
        yield sesion
    motor.dispose()


def emergencia(id, estado, registro, caso=None, prioridad=None):
    return Emergencia(id=id, estado=estado, fecha_hora_registro=registro, bonita_case_id=caso,
                      prioridad=prioridad, nivel_gravedad="alta", zona_afectada=f"Zona {id}",
                      descripcion_inicial="Descripción", publicada=True)


def cargar_escenario(db):
    db.add_all([Organizacion(id=1, nombre="ONG A"), Organizacion(id=2, nombre="ONG B")])
    db.add_all([
        emergencia(1, EstadoEmergencia.RESUELTA, F(2026, 10, 1, 10), "10"),
        # Selección preparada pero no confirmada en Bonita.
        emergencia(2, EstadoEmergencia.ESPERANDO_ADJUDICACION, F(2026, 10, 5), "20", prioridad=4),
        emergencia(3, EstadoEmergencia.RESUELTA, F(2026, 10, 10), "30"),
        emergencia(4, EstadoEmergencia.RESUELTA, F(2026, 10, 15)),
        emergencia(5, EstadoEmergencia.ESPERA_OFERTAS, F(2026, 10, 20, 23), "50", prioridad=6),
    ])
    db.add_all([
        LoteNecesidad(id=1, emergencia_id=1, tipo="agua", cantidad=100, unidad="litros"),
        LoteNecesidad(id=2, emergencia_id=1, tipo="agua", cantidad=10, unidad="bidones"),
        LoteNecesidad(id=3, emergencia_id=2, tipo="agua", cantidad=5, unidad="litros"),
        LoteRecursoCloud(lote_id=1, tipo_recurso_id=5),
        LoteRecursoCloud(lote_id=2, tipo_recurso_id=5),
    ])
    ofertado = F(2026, 10, 1, 12)
    db.add_all([
        OfertaAyuda(id=1, emergencia_id=1, organizacion_id=1, fecha_hora_oferta=ofertado,
                    adjudicada_en=F(2026, 9, 30)),
        OfertaAyuda(id=2, emergencia_id=1, organizacion_id=1, es_conjunta=True,
                    fecha_hora_oferta=ofertado, adjudicada_en=F(2026, 10, 2)),
        OfertaAyuda(id=3, emergencia_id=1, organizacion_id=2, fecha_hora_oferta=ofertado),
        OfertaAyuda(id=4, emergencia_id=2, organizacion_id=2, fecha_hora_oferta=ofertado,
                    adjudicada_en=F(2026, 10, 6)),
    ])
    db.add_all([
        OfertaItem(id=1, oferta_id=1, lote_necesidad_id=1, cantidad_ofrecida=60, finalizado_en=F(2026, 10, 3)),
        OfertaItem(id=2, oferta_id=1, lote_necesidad_id=2, cantidad_ofrecida=10),
        OfertaItem(id=3, oferta_id=2, lote_necesidad_id=1, cantidad_ofrecida=40),
        OfertaItem(id=4, oferta_id=3, lote_necesidad_id=1, cantidad_ofrecida=50),
        OfertaItem(id=5, oferta_id=4, lote_necesidad_id=3, cantidad_ofrecida=5),
        AporteOfertaItem(item_id=3, organizacion_id=1, cantidad=10),
        AporteOfertaItem(item_id=3, organizacion_id=2, cantidad=30),
        # La confirmación del aviso manda sobre adjudicada_en (que es de septiembre).
        AvisoAdjudicacion(oferta_id=1, creada_en=F(2026, 10, 2, 12)),
    ])
    db.add(EvaluacionCloud(
        emergencia_id=1, solicitud_id="s-1", caso_id="10", solicitud_json="{}", vigente=True,
        evaluacion_json=json.dumps({"emergencia_id": 1, "resultados": [
            {"oferta_id": 1, "lote_id": 1, "cantidad_verificada": 50},
            {"oferta_id": 1, "lote_id": 2, "cantidad_verificada": 10},
            {"oferta_id": 2, "lote_id": 1, "cantidad_verificada": 40},
            {"oferta_id": 3, "lote_id": 1, "cantidad_verificada": 20},
        ]}),
    ))
    db.add(RegistroRecursos(
        emergencia_id=1, caso_id="10", seleccion_json="[]", solicitud_json="{}", estado="CONFIRMADO",
        respuesta_json=json.dumps({"emergencia_id": 1, "lote_id": None, "total_bloqueado": 100,
                                   "bloqueados": [{"ong_id": 900, "item_id": 5, "cantidad": 100,
                                                   "estado": "BLOQUEADO"}]}),
    ))
    db.add(CierreEmergencia(emergencia_id=1, resuelta_en=F(2026, 10, 3, 10)))
    db.commit()


def tablero(db, monkeypatch, bonita=None, **filtros):
    simulado = AsyncMock(return_value=metricas_bonita()) if bonita is None else bonita
    monkeypatch.setattr(BONITA, simulado)
    return asyncio.run(TableroService().obtener_tablero(db, **filtros)).model_dump(mode="json")


def test_resumen_antiguedad_resolucion_y_evolucion(db, monkeypatch):
    resumen = tablero(db, monkeypatch)["resumen"]
    assert resumen["total"]["valor"] == 5
    assert resumen["abiertas"]["emergencias_incluidas"] == [2, 5]
    assert resumen["resueltas"]["emergencias_incluidas"] == [1, 3, 4]
    assert resumen["prioridad_promedio_abiertas"].items() >= {"valor": 5.0, "n": 2}.items()
    # Antigüedad: solo abiertas.
    assert resumen["antiguedad_abiertas_horas"]["n"] == 2
    assert resumen["antiguedad_abiertas_horas"]["emergencias_incluidas"] == [2, 5]
    # Resolución: 48 h con cierre local (E1) y 24 h con end_date de Bonita (E3).
    resolucion = resumen["resolucion_horas"]
    assert (resolucion["promedio"], resolucion["n"]) == (36.0, 2)
    assert resolucion["fuente_fecha"] == {"local": 1, "bonita": 1}
    assert resolucion["sin_fecha_cierre"] == [4]
    assert resolucion["emergencias_incluidas"] == [1, 3]
    assert {f["fecha"]: (f["aperturas"], f["cierres"]) for f in resumen["evolucion"]["filas"]} == {
        "2026-10-01": (1, 0), "2026-10-03": (0, 1), "2026-10-05": (1, 0),
        "2026-10-10": (1, 0), "2026-10-11": (0, 1), "2026-10-15": (1, 0), "2026-10-20": (1, 0),
    }
    for indicador in resumen.values():
        assert {"descripcion", "fuente", "alcance", "emergencias_incluidas"} <= set(indicador)


def test_cobertura_por_lote_confirmada_y_consorcio_una_vez(db, monkeypatch):
    filas = {f["lote_id"]: f for f in tablero(db, monkeypatch)["recursos"]["por_lote"]["filas"]}
    # Ofertado: todas las ofertas; verificado: ronda vigente; cubierto: solo confirmadas.
    assert filas[1].items() >= {"pedido": 100, "ofertado": 150, "verificado": 110,
                             "cubierto_confirmado": 90, "porcentaje_cobertura": 90.0, "unidad": "litros"}.items()
    assert filas[2].items() >= {"ofertado": 10, "verificado": 10, "cubierto_confirmado": 10, "unidad": "bidones"}.items()
    # Emergencia 2: oferta solo seleccionada (sin confirmar) y sin ronda local.
    assert filas[3].items() >= {"ofertado": 5, "verificado": None, "cubierto_confirmado": 0}.items()


def test_totales_verificado_reservado_entregado_por_unidad(db, monkeypatch):
    recursos = tablero(db, monkeypatch)["recursos"]
    filas = {(f["mes"], f["tipo_recurso_id"], f["unidad"]): f for f in recursos["totales"]["filas"]}
    litros = filas[("2026-10", 5, "litros")]
    assert (litros["ofertado"], litros["verificado"], litros["reservado"], litros["entregado"]) == (150, 110, 100, 50)
    bidones = filas[("2026-10", 5, "bidones")]
    assert (bidones["ofertado"], bidones["reservado"], bidones["entregado"]) == (10, 0, 0)
    assert filas[("2026-10", None, "litros")]["ofertado"] == 5
    assert recursos["etiqueta_recursos"] == "Recursos entregados"


def test_etiqueta_reservados_sin_entregas(db, monkeypatch):
    db.get(OfertaItem, 1).finalizado_en = None
    db.commit()
    assert tablero(db, monkeypatch)["recursos"]["etiqueta_recursos"] == "Recursos reservados"


def test_proyectos_solo_confirmados_consorcios_y_ranking_por_aportes(db, monkeypatch):
    proyectos = tablero(db, monkeypatch)["proyectos"]
    filas = proyectos["proyectos"]["filas"]
    assert [f["emergencia_id"] for f in filas] == [1]  # la emergencia 2 solo está seleccionada
    assert filas[0].items() >= {"items_totales": 3, "items_finalizados": 1, "resuelta": True,
                             "resolucion_horas": 48.0, "bonita_case_id": "10"}.items()
    assert filas[0]["cantidades"] == [
        {"tipo_recurso": "agua", "unidad": "bidones", "confirmado": 10, "entregado": 0},
        {"tipo_recurso": "agua", "unidad": "litros", "confirmado": 90, "entregado": 50},
    ]
    assert proyectos["consorcios"].items() >= {"emergencias_resueltas": 3, "resueltas_con_consorcio": 1,
                                            "porcentaje": 33.33}.items()
    assert [(f["organizacion_nombre"], f["unidad"], f["cantidad_confirmada"])
            for f in proyectos["ranking_ongs"]["filas"]] == [
        ("ONG A", "litros", 60.0), ("ONG B", "litros", 30.0), ("ONG A", "bidones", 10.0)]


def test_bonita_limitado_a_casos_filtrados(db, monkeypatch):
    simulado = AsyncMock(return_value=metricas_bonita())
    bonita = tablero(db, monkeypatch, bonita=simulado)["bonita"]
    assert simulado.await_args.args[0] == {"10", "20", "30", "50"}
    assert bonita.items() >= {"disponible": True, "casos_activos": 1, "casos_finalizados": 2,
                           "casos_cancelados": 1, "casos_camino_alternativo": 1}.items()
    assert bonita["tiempos_por_etapa"] == [{"etapa": "Generar lotes", "promedio_horas": 2.0, "n": 3},
                                           {"etapa": "Publicar pedido", "promedio_horas": None, "n": 0}]
    verificacion = {v["emergencia_id"]: v for v in bonita["verificacion"]}
    assert verificacion[1].items() >= {"estado_bonita": "completed", "resolucion_horas": 47.0}.items()
    assert verificacion[5].items() >= {"estado_bonita": "cancelado", "estado_local": "esperando_ofertas"}.items()
    tablero(db, monkeypatch, bonita=simulado, desde=F(2026, 10, 9))
    assert simulado.await_args.args[0] == {"30", "50"}


def test_bonita_no_disponible_no_rompe_el_tablero(db, monkeypatch):
    datos = tablero(db, monkeypatch, bonita=AsyncMock(side_effect=BonitaClientError("caído")))
    assert datos["bonita"].items() >= {"disponible": False, "error": "caído", "verificacion": []}.items()
    # Sin Bonita, la emergencia 3 no tiene fecha de cierre.
    assert datos["resumen"]["resolucion_horas"]["sin_fecha_cierre"] == [3, 4]
    assert datos["resumen"]["total"]["valor"] == 5


def test_hasta_sin_hora_incluye_el_dia_completo(db, monkeypatch):
    filtros = FiltrosReporte(desde=None, hasta=F(2026, 10, 20), nivel_gravedad=None, formato="json")
    assert filtros.hasta == F(2026, 10, 20, 23, 59, 59, 999999)
    datos = tablero(db, monkeypatch, desde=F(2026, 10, 20), hasta=filtros.hasta)
    assert datos["resumen"]["total"]["emergencias_incluidas"] == [5]


def test_resolver_escribe_cierre_una_sola_vez(db):
    repositorio = EmergenciaRepository()
    caso = db.get(Emergencia, 5)
    repositorio.resolver_emergencia(db, caso)
    primera = db.get(CierreEmergencia, 5).resuelta_en
    repositorio.resolver_emergencia(db, caso)
    assert db.get(CierreEmergencia, 5).resuelta_en == primera
    assert db.get(CierreEmergencia, 1).resuelta_en == F(2026, 10, 3, 10)


def test_endpoint_hasta_fecha_exportar_igual_y_permisos(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    monkeypatch.setattr(BONITA, AsyncMock(return_value=metricas_bonita()))
    with sesiones() as db:
        db.add(emergencia(3, EstadoEmergencia.ESPERA_OFERTAS, F(2026, 10, 20, 23)))
        db.commit()
    auditor = cabecera(AUDITOR)
    respuesta = cliente.get("/api/v1/reportes/tablero",
                            params={"desde": "2026-10-20", "hasta": "2026-10-20"}, headers=auditor)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["resumen"]["total"]["emergencias_incluidas"] == [3]
    # Fecha con zona: 20:00 -03:00 son las 23:00 UTC.
    respuesta = cliente.get("/api/v1/reportes/tablero", headers=auditor,
                            params={"desde": "2026-10-20T20:00:00-03:00", "hasta": "2026-10-20T20:00:00-03:00"})
    assert respuesta.json()["resumen"]["total"]["emergencias_incluidas"] == [3]

    tablero_json = cliente.get("/api/v1/reportes/tablero", headers=auditor).json()
    exportado = cliente.get("/api/v1/reportes/exportar", headers=auditor).json()
    tablero_json.pop("generado_en"), exportado.pop("generado_en")
    assert exportado == tablero_json

    csv = cliente.get("/api/v1/reportes/exportar", params={"formato": "csv"}, headers=auditor)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    for seccion in ("resumen.indicadores", "recursos.por_lote", "proyectos.ranking_ongs",
                    "bonita.casos", "bonita.verificacion"):
        assert f"SECCIÓN: {seccion}" in csv.text

    for rol in (OPERADOR, COORDINADOR, ONG):
        for ruta in ("/api/v1/reportes/tablero", "/api/v1/reportes/exportar"):
            assert cliente.get(ruta, headers=cabecera(rol)).status_code == 403
