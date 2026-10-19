"""Registro público local con autorización real y Cloud simulado."""

from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models import Organizacion
from app.services.permisos_service import COORDINADOR, ONG
from test_permisos_api import cabecera, entorno, estado

ALTA_ONG = {"nombre": "Ayuda comunitaria", "tipo": "ong",
            "cuit": "30-12345678-9", "email": "contacto@example.org",
            "telefono": "123456", "activa": True}
IDENTIDAD_CLOUD = {"id": 900, "cuit": ALTA_ONG["cuit"],
                   "razon_social": ALTA_ONG["nombre"], "email": ALTA_ONG["email"]}


@pytest.fixture
def entorno_ong(entorno, monkeypatch):
    remoto = Mock(return_value=httpx.Response(201, json=IDENTIDAD_CLOUD))
    monkeypatch.setattr(httpx, "post", remoto)
    monkeypatch.setenv("CLOUD_API_URL", "https://cloud.example.test/base/")
    return entorno[0], entorno[1], remoto


def test_registra_ong_cloud_antes_de_guardar_y_reenvia_token(entorno_ong):
    cliente, sesiones, remoto = entorno_ong
    encabezados = cabecera(COORDINADOR)

    def responder(*args, **kwargs):
        with sesiones() as db:
            assert db.query(Organizacion).count() == 2
        return httpx.Response(201, json=IDENTIDAD_CLOUD)

    remoto.side_effect = responder
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=encabezados)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {"id": 3, **{k: v for k, v in ALTA_ONG.items() if k != "cuit"}}
    remoto.assert_called_once_with(
        "https://cloud.example.test/base/ongs/registro",
        json={"cuit": ALTA_ONG["cuit"], "razon_social": ALTA_ONG["nombre"],
              "email": ALTA_ONG["email"]},
        headers=encabezados, timeout=10.0)
    with sesiones() as db:
        creada = db.query(Organizacion).filter_by(nombre=ALTA_ONG["nombre"]).one()
        assert creada.email == ALTA_ONG["email"] and creada.id != 900
        assert "cuit" not in Organizacion.__table__.columns


@pytest.mark.parametrize("campo,valor", [
    ("cuit", None), ("cuit", ""), ("cuit", "   "),
    ("email", None), ("email", ""), ("email", "invalido"),
])
def test_ong_requiere_cuit_y_email_antes_de_cloud(entorno_ong, campo, valor):
    cliente, sesiones, remoto = entorno_ong
    datos = dict(ALTA_ONG)
    if valor is None:
        datos.pop(campo)
    else:
        datos[campo] = valor
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=datos, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 422, respuesta.text
    assert estado(sesiones) == anterior
    remoto.assert_not_called()


@pytest.mark.parametrize("estado_cloud,esperado", [(409, 409), (401, 401), (403, 403),
                                                     (500, 503), (503, 503), (302, 503)])
def test_rechazo_cloud_no_crea_local_ni_filtra_detalles(entorno_ong, estado_cloud, esperado):
    cliente, sesiones, remoto = entorno_ong
    remoto.return_value = httpx.Response(estado_cloud, json={"detail": "secreto upstream"})
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == esperado, respuesta.text
    assert "secreto" not in respuesta.text
    if estado_cloud == 409:
        assert "CUIT" in respuesta.json()["detail"]
    assert estado(sesiones) == anterior
    remoto.assert_called_once()


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_fallo_transporte_no_crea_local(entorno_ong, error):
    cliente, sesiones, remoto = entorno_ong
    remoto.side_effect = error("secreto upstream")
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503 and "secreto" not in respuesta.text
    assert estado(sesiones) == anterior
    remoto.assert_called_once()


@pytest.mark.parametrize("cuerpo", [
    None, [], {}, {**IDENTIDAD_CLOUD, "id": True}, {**IDENTIDAD_CLOUD, "id": 0},
    {**IDENTIDAD_CLOUD, "id": "900"}, {**IDENTIDAD_CLOUD, "cuit": "ajeno"},
    {**IDENTIDAD_CLOUD, "razon_social": "Otra"}, {**IDENTIDAD_CLOUD, "email": "otro@example.org"},
])
def test_respuesta_cloud_malformada_no_crea_local(entorno_ong, cuerpo):
    cliente, sesiones, remoto = entorno_ong
    remoto.return_value = httpx.Response(201, json=cuerpo)
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503, respuesta.text
    assert estado(sesiones) == anterior
    remoto.assert_called_once()


def test_json_roto_cloud_no_crea_local(entorno_ong):
    cliente, sesiones, remoto = entorno_ong
    remoto.return_value = httpx.Response(201, content="no-json")
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503 and estado(sesiones) == anterior


@pytest.mark.parametrize("encabezados,esperado", [({}, 401),
    ({"Authorization": "Bearer invalido"}, 401), (cabecera(ONG), 403)])
def test_permisos_se_validan_antes_de_cloud(entorno_ong, encabezados, esperado):
    cliente, sesiones, remoto = entorno_ong
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=encabezados)
    assert respuesta.status_code == esperado and estado(sesiones) == anterior
    remoto.assert_not_called()


def test_fallo_local_revierte_y_no_finge_compensacion_cloud(entorno_ong, monkeypatch):
    cliente, sesiones, remoto = entorno_ong
    reversiones = []

    def fallar(self, db, organizacion):
        revertir = Mock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", revertir)
        reversiones.append(revertir)
        db.add(organizacion)
        db.flush()
        raise SQLAlchemyError("secreto persistencia")

    monkeypatch.setattr("app.repositories.OrganizacionRepository.crear", fallar)
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/organizaciones", json=ALTA_ONG, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 503 and "secreto" not in respuesta.text
    assert estado(sesiones) == anterior
    reversiones[0].assert_called_once()
    remoto.assert_called_once()


def test_no_ong_conserva_alta_sin_cloud_y_patch_lista_no_exigen_cuit(entorno_ong):
    cliente, sesiones, remoto = entorno_ong
    datos = {"nombre": "Municipio", "tipo": "municipio", "email": "sin-validar"}
    encabezados = cabecera(COORDINADOR)
    respuesta = cliente.post("/api/v1/organizaciones", json=datos, headers=encabezados)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {"id": 3, **datos, "telefono": None, "activa": True}
    assert cliente.patch("/api/v1/organizaciones/1", json={"telefono": "123"},
                         headers=encabezados).status_code == 200
    assert len(cliente.get("/api/v1/organizaciones").json()) == 3
    assert estado(sesiones)
    remoto.assert_not_called()


def test_ong_acepta_normalizacion_de_espacios_cloud(entorno_ong):
    cliente, _, remoto = entorno_ong
    datos = {**ALTA_ONG, **{campo: f"  {ALTA_ONG[campo]}  " for campo in ("cuit", "nombre", "email")}}
    respuesta = cliente.post("/api/v1/organizaciones", json=datos, headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 201, respuesta.text
    remoto.assert_called_once()
