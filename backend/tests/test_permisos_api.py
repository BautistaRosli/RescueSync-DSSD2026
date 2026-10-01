"""Pruebas de autorización HTTP con datos aislados e integraciones simuladas."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Emergencia,
    EstadoEmergencia,
    LoteNecesidad,
    OfertaAyuda,
    OfertaItem,
    Organizacion,
    RecursoInventario,
    Rol,
    Usuario,
)
from app.services.permisos_service import OPERADOR, COORDINADOR, ONG, AUDITOR
from app.services.security_service import JWT_SECRET, generar_token, hashear_password

ROLES = [OPERADOR, COORDINADOR, ONG, AUDITOR]
ALTA = {"nombre": "Nombre", "apellido": "Apellido", "email": "alta@example.org",
        "password": "clave-prueba-123", "rol_id": 1}
EMERGENCIA = {"zona_afectada": "Zona", "descripcion_inicial": "Descripción", "nivel_gravedad": "media"}
LOTE = {"tipo": "agua", "cantidad": 10}
OFERTA = {"emergencia_id": 2, "organizacion_id": 1, "items": []}
RECURSO = {"tipo": "agua", "cantidad_total": 10}

# Cada operación tiene datos válidos para que el caso permitido ejecute el servicio real.
CASOS = [
    ("POST", "/auth/registro", ALTA, [COORDINADOR]),
    ("GET", "/emergencias", None, ROLES),
    ("GET", "/emergencias/bandeja?publicada=false", None, [OPERADOR, COORDINADOR, AUDITOR]),
    ("GET", "/emergencias/1", None, [OPERADOR, COORDINADOR, AUDITOR]),
    ("POST", "/emergencias", EMERGENCIA, [OPERADOR]),
    ("PATCH", "/emergencias/1", {"zona_afectada": "Otra"}, [COORDINADOR]),
    ("POST", "/emergencias/1/publicar", None, [COORDINADOR]),
    ("POST", "/emergencias/1/bonita/iniciar", None, [COORDINADOR]),
    ("GET", "/emergencias/1/lotes", None, [OPERADOR, COORDINADOR, AUDITOR]),
    ("POST", "/emergencias/1/lotes", LOTE, [COORDINADOR]),
    ("GET", "/lotes/1", None, [OPERADOR, COORDINADOR, AUDITOR]),
    ("PATCH", "/lotes/1", {"cantidad": 12}, [COORDINADOR]),
    ("DELETE", "/lotes/1", None, [COORDINADOR]),
    ("GET", "/ofertas", None, [COORDINADOR, ONG, AUDITOR]),
    ("GET", "/ofertas/1", None, [COORDINADOR, ONG, AUDITOR]),
    ("POST", "/ofertas", OFERTA, [ONG]),
    ("PATCH", "/ofertas/1", {"observaciones": "Cambio"}, [ONG]),
    ("POST", "/ofertas/1/items/1/finalizar", None, [ONG]),
    ("GET", "/emergencias/2/ofertas", None, [COORDINADOR, ONG, AUDITOR]),
    ("GET", "/emergencias/2/ofertas/consolidadas", None, [COORDINADOR, AUDITOR]),
    ("POST", "/ofertas/1/adjudicar", None, [COORDINADOR, OPERADOR]),
    ("GET", "/organizaciones/1/inventario", None, [COORDINADOR, ONG, AUDITOR]),
    ("POST", "/organizaciones/1/inventario", RECURSO, [ONG]),
    ("PATCH", "/organizaciones/1/inventario/1", RECURSO, [ONG]),
    ("DELETE", "/organizaciones/1/inventario/1", None, [ONG]),
    ("GET", "/organizaciones", None, [COORDINADOR, ONG, AUDITOR]),
    ("GET", "/organizaciones/1", None, [COORDINADOR, ONG, AUDITOR]),
    ("POST", "/organizaciones", {"nombre": "Nueva"}, [COORDINADOR]),
    ("PATCH", "/organizaciones/1", {"nombre": "Modificada"}, [COORDINADOR]),
    ("POST", "/bonita/test-login", None, [COORDINADOR]),
    ("POST", "/bonita/test-variables", {"case_id": 10, "variables": {}}, [COORDINADOR]),
]


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as db:
        db.add_all([Rol(id=i, nombre=rol) for i, rol in enumerate(ROLES, 1)])
        db.add_all([Organizacion(id=1, nombre="Propia"), Organizacion(id=2, nombre="Ajena")])
        db.add_all([Usuario(id=i, email=f"usuario{i}@example.org", nombre="Nombre", apellido="Apellido",
                            password_hash="sin-login", rol_id=i, organizacion_id=1 if i == 3 else None)
                    for i in range(1, 5)])
        # La emergencia publicada queda esperando ofertas: con otro estado la
        # convocatoria está cerrada y las escrituras de ofertas darían 409.
        db.add_all([Emergencia(id=i, publicada=i == 2,
                               estado=EstadoEmergencia.ESPERA_OFERTAS if i == 2
                               else EstadoEmergencia.ESPERA_LOTES,
                               **EMERGENCIA) for i in (1, 2)])
        db.add_all([LoteNecesidad(id=i, emergencia_id=i, **LOTE) for i in (1, 2)])
        db.add_all([OfertaAyuda(id=i, emergencia_id=2, organizacion_id=i) for i in (1, 2)])
        # Ítem de la oferta 1 sobre el lote 2 (emergencia 2): sin ítems la
        # adjudicación responde 400 y el caso permitido no llegaría a 200.
        db.add(OfertaItem(id=1, oferta_id=1, lote_necesidad_id=2, cantidad_ofrecida=5))
        # Recurso de la organización 1, la del usuario con rol ONG (id 3),
        # para que PATCH y DELETE del inventario fallen por permisos y no por 404.
        db.add(RecursoInventario(id=1, organizacion_id=1, **RECURSO))
        db.commit()

    def obtener_db():
        with sesiones() as db:
            yield db

    correo = Mock()
    adjudicacion = Mock()
    bonita = AsyncMock(return_value=42)
    variables = AsyncMock(return_value=[])
    diagnostico = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.services.emergencias_service.notificar_nueva_emergencia", correo)
    monkeypatch.setattr("app.services.ofertas_service.notificar_adjudicacion", adjudicacion)
    monkeypatch.setattr("app.services.emergencias_service.bonita_client.start_emergency_process", bonita)
    monkeypatch.setattr("app.services.emergencias_service.bonita_client.set_case_variables", variables)
    monkeypatch.setattr("app.api.routes.bonita_api.verificar_conexion", diagnostico)
    monkeypatch.setattr("app.api.routes.bonita_api.setear_variables_prueba", variables)
    app.dependency_overrides[get_db] = obtener_db
    # Sin lifespan: la siembra utiliza exclusivamente nuestra base en memoria.
    cliente = TestClient(app)
    yield cliente, sesiones, (correo, adjudicacion, bonita, variables, diagnostico)
    cliente.close()
    app.dependency_overrides.clear()
    motor.dispose()


def cabecera(rol):
    identificador = ROLES.index(rol) + 1
    return {"Authorization": f"Bearer {generar_token(identificador, identificador, rol)}"}


def estado(sesiones):
    with sesiones() as db:
        return [list(db.execute(tabla.select())) for tabla in Base.metadata.sorted_tables]


@pytest.mark.parametrize("metodo,ruta,cuerpo,permitidos", CASOS)
@pytest.mark.parametrize("rol", ROLES)
def test_matriz_roles(entorno, metodo, ruta, cuerpo, permitidos, rol):
    cliente, sesiones, externos = entorno
    anterior = estado(sesiones)
    respuesta = cliente.request(metodo, "/api/v1" + ruta, json=cuerpo, headers=cabecera(rol))
    if rol in permitidos:
        assert respuesta.status_code in (200, 201, 204), respuesta.text
    else:
        assert respuesta.status_code == 403, respuesta.text
        assert estado(sesiones) == anterior
        assert all(mock.call_count == 0 for mock in externos)


@pytest.mark.parametrize("metodo,ruta,cuerpo,permitidos", CASOS)
@pytest.mark.parametrize("tipo", ["anonimo", "invalido", "vencido", "inactivo"])
def test_autenticacion_todas_las_rutas(entorno, metodo, ruta, cuerpo, permitidos, tipo):
    cliente, sesiones, externos = entorno
    encabezados = {}
    if tipo == "invalido":
        encabezados = {"Authorization": "Bearer no-es-jwt"}
    elif tipo == "vencido":
        token = jwt.encode({"sub": "2", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, JWT_SECRET, algorithm="HS256")
        encabezados = {"Authorization": f"Bearer {token}"}
    elif tipo == "inactivo":
        with sesiones() as db:
            db.get(Usuario, 2).activo = False
            db.commit()
        encabezados = cabecera(COORDINADOR)
    anterior = estado(sesiones)
    respuesta = cliente.request(metodo, "/api/v1" + ruta, json=cuerpo, headers=encabezados)
    assert respuesta.status_code == (403 if tipo == "inactivo" else 401), respuesta.text
    assert estado(sesiones) == anterior
    assert all(mock.call_count == 0 for mock in externos)


@pytest.mark.parametrize("ruta", ["/ofertas/2", "/ofertas?organizacion_id=2", "/organizaciones/2",
                                  "/emergencias/1", "/emergencias/1/lotes", "/lotes/1",
                                  "/emergencias/bandeja?publicada=false", "/emergencias?publicada=false"])
def test_ong_no_accede_a_datos_ajenos(entorno, ruta):
    assert entorno[0].get("/api/v1" + ruta, headers=cabecera(ONG)).status_code == 403


def test_listados_filtran_antes_de_devolver_y_contar(entorno):
    cliente = entorno[0]
    for rol, identificador in ((OPERADOR, 1), (ONG, 2)):
        assert [e["id"] for e in cliente.get("/api/v1/emergencias", headers=cabecera(rol)).json()] == [identificador]
        publicada = "true" if rol == ONG else "false"
        datos = cliente.get(f"/api/v1/emergencias/bandeja?publicada={publicada}&por_pagina=1", headers=cabecera(rol)).json()
        assert datos["total"] == 1 and datos["paginas"] == 1 and datos["items"][0]["id"] == identificador
    for ruta in ("/ofertas", "/emergencias/2/ofertas", "/organizaciones"):
        assert [d["id"] for d in cliente.get("/api/v1" + ruta, headers=cabecera(ONG)).json()] == [1]


def test_ong_no_puede_escribir_ofertas_ajenas_o_no_publicadas(entorno):
    cliente, sesiones, _ = entorno
    anterior = estado(sesiones)
    for cuerpo in ({**OFERTA, "organizacion_id": 2}, {**OFERTA, "emergencia_id": 1}):
        assert cliente.post("/api/v1/ofertas", json=cuerpo, headers=cabecera(ONG)).status_code == 403
    assert cliente.patch("/api/v1/ofertas/2", json={"observaciones": "Ataque"}, headers=cabecera(ONG)).status_code == 403
    assert estado(sesiones) == anterior
    respuesta = cliente.patch("/api/v1/ofertas/1", json={"items": [{"lote_necesidad_id": 1, "cantidad_ofrecida": 1}]}, headers=cabecera(ONG))
    assert respuesta.status_code == 400
    assert estado(sesiones) == anterior


def test_convocatoria_cerrada_bloquea_ofertas_pero_no_finalizar(entorno):
    """Fuera del estado esperando_ofertas no se cargan ni modifican ofertas.

    Cerrar la actividad de un ítem sí sigue permitido: ocurre después del
    cierre de la convocatoria.
    """
    cliente, sesiones, _ = entorno
    with sesiones() as db:
        db.get(Emergencia, 2).estado = EstadoEmergencia.RESUELTA
        db.commit()
    cerrada = "La convocatoria está cerrada: no se pueden cargar ni modificar ofertas"
    creacion = cliente.post("/api/v1/ofertas", json=OFERTA, headers=cabecera(ONG))
    assert creacion.status_code == 409 and creacion.json()["detail"] == cerrada
    edicion = cliente.patch("/api/v1/ofertas/1", json={"observaciones": "Cambio"},
                            headers=cabecera(ONG))
    assert edicion.status_code == 409 and edicion.json()["detail"] == cerrada
    finalizacion = cliente.post("/api/v1/ofertas/1/items/1/finalizar", headers=cabecera(ONG))
    assert finalizacion.status_code == 200, finalizacion.text
    assert finalizacion.json()["finalizado_en"]


def test_rol_y_organizacion_se_resuelven_desde_bd(entorno):
    cliente, sesiones, _ = entorno
    encabezados = cabecera(COORDINADOR)
    with sesiones() as db:
        db.get(Usuario, 2).rol_id = 4
        db.get(Usuario, 3).organizacion_id = 2
        db.commit()
    assert cliente.post("/api/v1/organizaciones", json={"nombre": "No"}, headers=encabezados).status_code == 403
    assert cliente.get("/api/v1/ofertas/1", headers=cabecera(ONG)).status_code == 403
    assert cliente.get("/api/v1/ofertas/2", headers=cabecera(ONG)).status_code == 200


@pytest.mark.parametrize("ambiente", [None, "production", "staging"])
def test_diagnosticos_solo_development(entorno, monkeypatch, ambiente):
    if ambiente is None:
        monkeypatch.delenv("APP_ENV")
    else:
        monkeypatch.setenv("APP_ENV", ambiente)
    cliente, _, externos = entorno
    for ruta, cuerpo in (("test-login", None), ("test-variables", {"case_id": 1, "variables": {}})):
        assert cliente.post("/api/v1/bonita/" + ruta, json=cuerpo, headers=cabecera(COORDINADOR)).status_code == 404
    assert all(mock.call_count == 0 for mock in externos)
    assert cliente.get("/api/v1/bonita/test-login", headers=cabecera(COORDINADOR)).status_code == 405


def test_registro_ong_exige_organizacion_valida_y_conserva_contrato(entorno):
    cliente = entorno[0]
    encabezados = cabecera(COORDINADOR)
    datos = {**ALTA, "rol_id": 3}
    assert cliente.post("/api/v1/auth/registro", json=datos, headers=encabezados).status_code == 400
    assert cliente.post("/api/v1/auth/registro", json={**datos, "organizacion_id": 999}, headers=encabezados).status_code == 404
    respuesta = cliente.post("/api/v1/auth/registro", json={**datos, "organizacion_id": 1}, headers=encabezados)
    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == ONG and respuesta.json()["access_token"]


@pytest.mark.parametrize("datos,algoritmo,secreto", [
    ({"sub": "2"}, "HS256", JWT_SECRET),
    ({"exp": 9999999999}, "HS256", JWT_SECRET),
    ({"sub": "2", "exp": 9999999999}, "HS384", JWT_SECRET),
    ({"sub": "2", "exp": 9999999999}, "HS256", "otra-clave-de-prueba-de-al-menos-32-bytes"),
    ({"sub": "999", "exp": 9999999999}, "HS256", JWT_SECRET),
    ({"sub": "2", "exp": None}, "HS256", JWT_SECRET),
    ({"sub": "2", "exp": "incorrecta"}, "HS256", JWT_SECRET),
    ({"sub": "2", "exp": []}, "HS256", JWT_SECRET),
])
def test_claims_firma_algoritmo_y_usuario(entorno, datos, algoritmo, secreto):
    token = jwt.encode(datos, secreto, algorithm=algoritmo)
    assert entorno[0].get("/api/v1/emergencias", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_endpoints_publicos_y_login(entorno):
    cliente, sesiones, _ = entorno
    assert cliente.get("/").status_code == 200
    assert cliente.get("/api/v1/roles").status_code == 200
    with sesiones() as db:
        db.get(Usuario, 2).password_hash = hashear_password("clave-prueba-123")
        db.commit()
    datos = {"email": "usuario2@example.org", "password": "clave-prueba-123"}
    assert cliente.post("/api/v1/auth/login", json=datos).status_code == 200
    assert cliente.post("/api/v1/auth/login", json={**datos, "password": "otra-clave"}).status_code == 401
