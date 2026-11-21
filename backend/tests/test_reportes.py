from datetime import datetime, timedelta, timezone

from app.models import Emergencia
from app.services.permisos_service import AUDITOR

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
