from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Emergencia, EstadoEmergencia, LoteNecesidad, OfertaAyuda, OfertaItem, Organizacion
from app.services.reportes_service import ReportesService


@pytest.fixture
def db():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as sesion:
        yield sesion
    motor.dispose()


@pytest.fixture
def emergencia(db):
    valor = Emergencia(id=1, nivel_gravedad="alta", zona_afectada="Zona", descripcion_inicial="Descripción",
                       estado=EstadoEmergencia.ESPERA_OFERTAS, publicada=True)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def lote(db, emergencia):
    valor = LoteNecesidad(id=1, emergencia_id=emergencia.id, tipo="agua", cantidad=10)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def oferta(db, emergencia):
    db.add(Organizacion(id=1, nombre="ONG"))
    valor = OfertaAyuda(id=1, emergencia_id=emergencia.id, organizacion_id=1)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def item(db, lote, oferta):
    valor = OfertaItem(id=1, oferta_id=oferta.id, lote_necesidad_id=lote.id, cantidad_ofrecida=1)
    db.add(valor)
    db.commit()
    return valor


def test_reportes_sin_datos_devuelve_ceros_y_listas_vacias(db):
    servicio = ReportesService()
    assert servicio.consorcios(db).model_dump() == {
        "total_ofertas_adjudicadas": 0, "ofertas_conjuntas": 0, "porcentaje_consorcios": 0
    }
    assert servicio.tiempo_publicacion(db).model_dump() == {
        "promedio_horas": 0, "minimo_horas": 0, "maximo_horas": 0
    }


def test_reportes_agrega_oferta_adjudicada_y_cobertura(db, emergencia, lote, oferta, item):
    ahora = datetime.now(timezone.utc)
    emergencia.fecha_publicacion = ahora - timedelta(hours=4)
    emergencia.estado = EstadoEmergencia.RESUELTA
    oferta.adjudicada_en = ahora
    item.cantidad_ofrecida = 7
    item.finalizado_en = ahora
    db.commit()
    servicio = ReportesService()
    assert servicio.cobertura_lotes(db).lotes[0].cantidad_ofrecida == 7
    assert servicio.proyectos(db)[0].items_finalizados == 1
    assert servicio.tiempo_adjudicacion(db).promedio_horas == 4
from app.models import Emergencia
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR

from test_permisos_api import cabecera, entorno


def test_reportes_exponen_metricas_del_dashboard(entorno):
    cliente = entorno[0]
    cabecera_auditor = cabecera(AUDITOR)

    respuesta = cliente.get(
        "/api/v1/reportes/emergencias", headers=cabecera_auditor
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == [
        {
            "estado": "esperando_lotes",
            "nivel_gravedad": "media",
            "cantidad": 1,
        },
        {
            "estado": "esperando_ofertas",
            "nivel_gravedad": "media",
            "cantidad": 1,
        },
    ]

    for ruta in (
        "/reportes/suministros-movilizados",
        "/reportes/ranking-ongs",
        "/reportes/demanda-oferta",
    ):
        respuesta = cliente.get("/api/v1" + ruta, headers=cabecera_auditor)
        assert respuesta.status_code == 200, respuesta.text
        assert isinstance(respuesta.json(), list)

    assert cliente.get(
        "/api/v1/reportes/consorcios", headers=cabecera_auditor
    ).json() == {
        "total_ofertas_adjudicadas": 0,
        "ofertas_conjuntas_adjudicadas": 0,
        "porcentaje_consorcios": 0.0,
    }


def test_nuevos_reportes_exponen_contratos_del_dashboard(entorno):
    cliente = entorno[0]
    cabecera_auditor = cabecera(AUDITOR)

    respuesta = cliente.get(
        "/api/v1/reportes/activas-resueltas", headers=cabecera_auditor
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"activas": 2, "resueltas": 0}

    respuesta = cliente.get(
        "/api/v1/reportes/evolucion-abiertas-resueltas",
        headers=cabecera_auditor,
    )
    assert respuesta.status_code == 200, respuesta.text
    assert all(set(item) == {"fecha", "abiertas", "resueltas"} for item in respuesta.json())

    respuesta = cliente.get(
        "/api/v1/reportes/necesidades-actuales", headers=cabecera_auditor
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == [
        {
            "tipo_recurso": "agua",
            "tipo_recurso_id": None,
            "cantidad_requerida": 20,
        }
    ]

    respuesta = cliente.get(
        "/api/v1/reportes/tiempo-vida", headers=cabecera_auditor
    )
    assert respuesta.status_code == 200, respuesta.text
    assert set(respuesta.json()) == {"promedio_horas"}

    respuesta = cliente.get(
        "/api/v1/reportes/prioridad-abiertas", headers=cabecera_auditor
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "promedio_prioridad": 0.0,
        "cantidad_emergencias": 0,
    }


def test_reportes_aceptan_filtros_de_fecha_y_gravedad(entorno):
    cliente = entorno[0]
    encabezados = cabecera(AUDITOR)
    respuesta = cliente.get(
        "/api/v1/reportes/emergencias",
        params={
            "desde": "2000-01-01T00:00:00Z",
            "hasta": "2100-01-01T00:00:00Z",
            "nivel_gravedad": "media",
        },
        headers=encabezados,
    )
    assert respuesta.status_code == 200, respuesta.text
    assert sum(item["cantidad"] for item in respuesta.json()) == 2

    filtrado = cliente.get(
        "/api/v1/reportes/emergencias",
        params={"nivel_gravedad": "alta"},
        headers=encabezados,
    )
    assert filtrado.status_code == 200, filtrado.text
    assert filtrado.json() == []

    assert cliente.get(
        "/api/v1/reportes/emergencias",
        params={"desde": "2025-01-02T00:00:00Z", "hasta": "2025-01-01T00:00:00Z"},
        headers=encabezados,
    ).status_code == 422
    assert cliente.get(
        "/api/v1/reportes/emergencias",
        params={"nivel_gravedad": "invalida"},
        headers=encabezados,
    ).status_code == 422


def test_todos_los_reportes_exportan_csv_con_descarga(entorno):
    cliente = entorno[0]
    encabezados = cabecera(AUDITOR)
    rutas = (
        "/emergencias", "/suministros-movilizados", "/consorcios",
        "/ranking-ongs", "/demanda-oferta", "/activas-resueltas",
        "/evolucion-abiertas-resueltas", "/necesidades-actuales",
        "/tiempo-vida", "/prioridad-abiertas",
    )
    for ruta in rutas:
        respuesta = cliente.get(
            "/api/v1/reportes" + ruta,
            params={"formato": "csv"},
            headers=encabezados,
        )
        assert respuesta.status_code == 200, f"{ruta}: {respuesta.text}"
        assert respuesta.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in respuesta.headers["content-disposition"]
        assert respuesta.text.splitlines()[0]


def test_reportes_rechazan_formato_invalido_y_conservan_permisos(entorno):
    cliente = entorno[0]
    assert cliente.get(
        "/api/v1/reportes/emergencias", params={"formato": "xml"},
        headers=cabecera(AUDITOR),
    ).status_code == 422
    for rol in (OPERADOR, COORDINADOR, ONG):
        assert cliente.get(
            "/api/v1/reportes/emergencias", params={"formato": "csv"},
            headers=cabecera(rol),
        ).status_code == 403


def test_exportar_reporte_completo_devuelve_el_tablero(entorno):
    cliente = entorno[0]
    respuesta = cliente.get(
        "/api/v1/reportes/exportar",
        params={"nivel_gravedad": "media"},
        headers=cabecera(AUDITOR),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"generado_en", "filtros", "resumen", "recursos", "proyectos", "bonita"}
    assert cuerpo["resumen"]["abiertas"]["valor"] == 2
    assert cuerpo["resumen"]["resueltas"]["valor"] == 0


def test_exportar_reporte_completo_csv_es_unico_archivo_con_secciones(entorno):
    respuesta = entorno[0].get(
        "/api/v1/reportes/exportar",
        params={"formato": "csv", "desde": "2020-01-01T00:00:00Z"},
        headers=cabecera(AUDITOR),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert respuesta.headers["content-disposition"] == 'attachment; filename="reporte-completo.csv"'
    assert respuesta.text.count("SECCIÓN:") == 11
    assert "SECCIÓN: proyectos.consorcios" in respuesta.text
    assert "SECCIÓN: bonita.verificacion" in respuesta.text


def test_exportar_reporte_completo_rechaza_roles_no_auditores(entorno):
    cliente = entorno[0]
    for rol in (OPERADOR, COORDINADOR, ONG):
        respuesta = cliente.get("/api/v1/reportes/exportar", headers=cabecera(rol))
        assert respuesta.status_code == 403, respuesta.text
