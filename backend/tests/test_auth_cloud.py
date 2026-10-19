"""Contrato público de sesión con Cloud, sin redes ni bases del usuario."""

import time
from unittest.mock import Mock

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Rol, Usuario
from app.services.security_service import JWT_SECRET, hashear_password

ALTA = {"email": "alta@example.org", "password": "clave-prueba-123",
        "nombre": "Nombre", "apellido": "Apellido", "rol_id": 1}
LOGIN = {"email": "local@example.org", "password": "clave-prueba-123"}


def token_cloud(email=LOGIN["email"], **cambios):
    datos = {"sub": "9876", "usuario": email, "iat": int(time.time()),
             "exp": int(time.time()) + 3600, "iss": "rescuesync-cloud",
             "aud": ["rescuesync-cloud", "rescuesync-backend"],
             "rol": "DIRECTOR_AUDITOR", "rol_id": 99}
    datos.update(cambios)
    return jwt.encode(datos, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def entorno_cloud(monkeypatch):
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as db:
        db.add(Rol(id=1, nombre="OPERADOR_MUNICIPAL"))
        db.add(Rol(id=2, nombre="REPRESENTANTE_ONG"))
        db.add(Usuario(id=7, email=LOGIN["email"], nombre="Perfil", apellido="Local",
                       password_hash=hashear_password(LOGIN["password"]), rol_id=1,
                       activo=True))
        db.commit()

    def obtener_db():
        with sesiones() as db:
            yield db

    def responder(url, *, json, timeout):
        assert timeout > 0
        assert json.keys() == {"usuario", "password"}
        if url.endswith("/auth/registro"):
            return httpx.Response(201, json={"id": 9876, "usuario": json["usuario"]})
        assert url.endswith("/auth/login")
        return httpx.Response(200, json={"access_token": token_cloud(json["usuario"]),
                                       "token_type": "bearer", "expires_in": 3600})

    remoto = Mock(side_effect=responder)
    monkeypatch.setattr(httpx, "post", remoto)
    app.dependency_overrides[get_db] = obtener_db
    cliente = TestClient(app, raise_server_exceptions=False)
    yield cliente, sesiones, remoto
    cliente.close()
    app.dependency_overrides.clear()
    motor.dispose()


def test_login_devuelve_mismo_jwt_y_me_busca_email_no_sub(entorno_cloud):
    cliente, _, remoto = entorno_cloud
    token = token_cloud()
    remoto.return_value = httpx.Response(200, json={"access_token": token,
                                      "token_type": "bearer", "expires_in": 3600})
    remoto.side_effect = None
    respuesta = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["access_token"] == token and cuerpo["token_type"] == "bearer"
    assert cuerpo["rol"] == "OPERADOR_MUNICIPAL" and cuerpo["usuario"]["id"] == 7
    me = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json() == cuerpo["usuario"]
    remoto.assert_called_once()
    assert remoto.call_args.kwargs["json"] == {"usuario": LOGIN["email"], "password": LOGIN["password"]}


@pytest.mark.parametrize("estado", [401, 500, 503, 302])
def test_cloud_rechaza_sin_fallback_local(entorno_cloud, estado):
    cliente, sesiones, remoto = entorno_cloud
    remoto.side_effect = None
    remoto.return_value = httpx.Response(estado, json={"detail": "secreto upstream"})
    respuesta = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert respuesta.status_code == (401 if estado == 401 else 503)
    assert "access_token" not in respuesta.json() and "secreto" not in respuesta.text
    with sesiones() as db:
        assert db.query(Usuario).count() == 1


@pytest.mark.parametrize("respuesta", [
    httpx.Response(200, content="no-json"), httpx.Response(200, json=[]),
    httpx.Response(200, json={}),
    httpx.Response(200, json={"access_token": "inválido", "token_type": "bearer", "expires_in": 3600}),
    httpx.Response(200, json={"access_token": token_cloud("ajeno@example.org"), "token_type": "bearer", "expires_in": 3600}),
    httpx.Response(200, json={"access_token": token_cloud(), "token_type": "otro", "expires_in": 3600}),
    httpx.Response(200, json={"access_token": token_cloud(), "token_type": "bearer", "expires_in": 0}),
])
def test_respuesta_cloud_invalida_no_entrega_sesion(entorno_cloud, respuesta):
    cliente, _, remoto = entorno_cloud
    remoto.side_effect = None
    remoto.return_value = respuesta
    resultado = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert resultado.status_code == 503 and "access_token" not in resultado.json()


def test_timeout_cloud_no_entrega_sesion(entorno_cloud):
    cliente, _, remoto = entorno_cloud
    remoto.side_effect = httpx.ReadTimeout("contraseña secreta")
    respuesta = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert respuesta.status_code == 503 and "secreta" not in respuesta.text


@pytest.mark.parametrize("cambios", [
    {"iss": "otro"}, {"aud": "otro"}, {"usuario": "ausente@example.org"},
    {"usuario": None}, {"usuario": 7}, {"sub": ""}, {"sub": 7},
    {"exp": 1}, {"iat": int(time.time()) + 3600},
])
def test_guard_rechaza_claims_cloud_invalidos(entorno_cloud, cambios):
    respuesta = entorno_cloud[0].get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token_cloud(**cambios)}"})
    assert respuesta.status_code == 401


def test_guard_rechaza_token_local_viejo_y_firma_alterada(entorno_cloud):
    cliente = entorno_cloud[0]
    viejo = jwt.encode({"sub": "7", "iat": int(time.time()), "exp": int(time.time()) + 100},
                       JWT_SECRET, algorithm="HS256")
    falso = token_cloud().split(".")
    falso[2] = ("A" if falso[2][0] != "A" else "B") + falso[2][1:]
    for token in (viejo, ".".join(falso)):
        assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_perfil_inexistente_e_inactivo(entorno_cloud):
    cliente, sesiones, _ = entorno_cloud
    assert cliente.post("/api/v1/auth/login", json={**LOGIN, "email": "ausente@example.org"}).status_code == 401
    with sesiones() as db:
        db.get(Usuario, 7).activo = False
        db.commit()
    assert cliente.post("/api/v1/auth/login", json=LOGIN).status_code == 403
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_cloud()}"}).status_code == 403


def test_registro_crea_credenciales_y_perfil_sin_hash_local(entorno_cloud):
    cliente, sesiones, remoto = entorno_cloud
    token = token_cloud(ALTA["email"])
    remoto.side_effect = [httpx.Response(201, json={"id": 9876, "usuario": ALTA["email"]}),
                         httpx.Response(200, json={"access_token": token, "token_type": "bearer", "expires_in": 3600})]
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["access_token"] == token
    assert respuesta.json()["rol"] == "OPERADOR_MUNICIPAL"
    assert [llamada.args[0].split("/")[-1] for llamada in remoto.call_args_list] == ["registro", "login"]
    with sesiones() as db:
        usuario = db.query(Usuario).filter_by(email=ALTA["email"]).one()
        assert usuario.password_hash == "!cloud" and usuario.id != 9876


@pytest.mark.parametrize("cambios,estado", [
    ({"email": LOGIN["email"]}, 409), ({"rol_id": 999}, 404),
    ({"rol_id": 2}, 400), ({"organizacion_id": 999}, 404),
])
def test_registro_valida_local_antes_de_cloud(entorno_cloud, cambios, estado):
    cliente, sesiones, remoto = entorno_cloud
    respuesta = cliente.post("/api/v1/auth/registro", json={**ALTA, **cambios})
    assert respuesta.status_code == estado
    remoto.assert_not_called()
    with sesiones() as db:
        assert db.query(Usuario).count() == 1


@pytest.mark.parametrize("cuerpo", [None, [], {}, {"id": 9876, "usuario": "ajeno@example.org"}])
def test_registro_rechaza_respuesta_cloud_malformada(entorno_cloud, cuerpo):
    cliente, sesiones, remoto = entorno_cloud
    remoto.side_effect = None
    remoto.return_value = httpx.Response(201, json=cuerpo)
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == 503
    remoto.assert_called_once()
    with sesiones() as db:
        assert db.query(Usuario).count() == 1


@pytest.mark.parametrize("claim", ["sub", "usuario", "iat", "exp", "iss", "aud"])
def test_guard_exige_claims_cloud(entorno_cloud, claim):
    datos = jwt.decode(token_cloud(), JWT_SECRET, algorithms=["HS256"],
                       audience="rescuesync-backend")
    datos.pop(claim)
    token = jwt.encode(datos, JWT_SECRET, algorithm="HS256")
    assert entorno_cloud[0].get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("login_correcto", [True, False])
def test_registro_cloud_existente_exige_mismas_credenciales(entorno_cloud, login_correcto):
    cliente, sesiones, remoto = entorno_cloud
    remoto.side_effect = [httpx.Response(409), httpx.Response(
        200 if login_correcto else 401,
        json={"access_token": token_cloud(ALTA["email"]), "token_type": "bearer", "expires_in": 3600})]
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == (201 if login_correcto else 401)
    with sesiones() as db:
        assert db.query(Usuario).count() == (2 if login_correcto else 1)


@pytest.mark.parametrize("fallo", ["registro", "token", "persistencia"])
def test_registro_no_guarda_perfil_incompleto(entorno_cloud, monkeypatch, fallo):
    cliente, sesiones, remoto = entorno_cloud
    reversiones = []
    if fallo == "registro":
        remoto.side_effect = httpx.ConnectError("sin servicio")
    elif fallo == "token":
        remoto.side_effect = [httpx.Response(201, json={"id": 9876, "usuario": ALTA["email"]}),
                             httpx.Response(200, json={"access_token": "roto", "token_type": "bearer", "expires_in": 3600})]
    else:
        def fallar(self, db, usuario):
            revertir = Mock(wraps=db.rollback)
            monkeypatch.setattr(db, "rollback", revertir)
            reversiones.append(revertir)
            db.add(usuario)
            db.flush()
            raise SQLAlchemyError("persistencia interrumpida")
        monkeypatch.setattr("app.repositories.UsuarioRepository.crear", fallar)
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == 503
    assert "access_token" not in respuesta.json()
    with sesiones() as db:
        assert db.query(Usuario).count() == 1
    if fallo == "persistencia":
        reversiones[0].assert_called_once()
