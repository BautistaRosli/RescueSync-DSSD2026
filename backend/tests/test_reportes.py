from datetime import datetime, timedelta, timezone

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


def test_exportar_reporte_completo_devuelve_las_diez_metricas_sin_ids_nacionales(entorno):
    cliente = entorno[0]
    respuesta = cliente.get(
        "/api/v1/reportes/exportar",
        params={"nivel_gravedad": "media"},
        headers=cabecera(AUDITOR),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {
        "emergencias_por_estado_y_gravedad",
        "recursos_adjudicados_por_mes",
        "participacion_consorcios",
        "ranking_ongs",
        "demanda_vs_oferta_por_recurso",
        "emergencias_activas_vs_resueltas",
        "evolucion_abiertas_y_resueltas",
        "necesidades_actuales",
        "tiempo_medio_de_vida",
        "promedio_prioridad_abiertas",
    }
    assert "tipo_recurso_id" not in respuesta.text
    assert cuerpo["emergencias_activas_vs_resueltas"] == {"activas": 2, "resueltas": 0}


def test_exportar_reporte_completo_csv_es_unico_archivo_con_secciones(entorno):
    respuesta = entorno[0].get(
        "/api/v1/reportes/exportar",
        params={"formato": "csv", "desde": "2020-01-01T00:00:00Z"},
        headers=cabecera(AUDITOR),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert respuesta.headers["content-disposition"] == 'attachment; filename="reporte-completo.csv"'
    assert respuesta.text.count("SECCIÓN:") == 10
    assert "tipo_recurso_id" not in respuesta.text
    assert "SECCIÓN: participacion_consorcios" in respuesta.text
    assert "SECCIÓN: promedio_prioridad_abiertas" in respuesta.text


def test_exportar_reporte_completo_rechaza_roles_no_auditores(entorno):
    cliente = entorno[0]
    for rol in (OPERADOR, COORDINADOR, ONG):
        respuesta = cliente.get("/api/v1/reportes/exportar", headers=cabecera(rol))
        assert respuesta.status_code == 403, respuesta.text
