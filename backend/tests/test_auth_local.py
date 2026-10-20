"""Sesiones locales aisladas: Cloud no participa de la identidad de personas."""

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
from app.services.security_service import JWT_SECRET, hashear_password, verificar_password
from app.services.usuarios_service import AuthService, RolService, USUARIOS_INICIALES

ALTA = {"email": "alta@example.org", "password": "clave-prueba-123",
        "nombre": "Nombre", "apellido": "Apellido", "rol_id": 1}
LOGIN = {"email": "local@example.org", "password": "clave-prueba-123"}


def token_local(**cambios):
    datos = {"sub": "7", "iat": int(time.time()), "exp": int(time.time()) + 3600,
             "iss": "rescuesync-local", "aud": "rescuesync-local-api"}
    datos.update(cambios)
    return jwt.encode(datos, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def entorno_local(monkeypatch):
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as db:
        db.add_all([Rol(id=1, nombre="OPERADOR_MUNICIPAL"),
                    Rol(id=2, nombre="REPRESENTANTE_ONG")])
        db.add(Usuario(id=7, email=LOGIN["email"], nombre="Perfil", apellido="Local",
                       password_hash=hashear_password(LOGIN["password"]), rol_id=1,
                       activo=True))
        db.commit()

    def obtener_db():
        with sesiones() as db:
            yield db

    remoto = Mock(side_effect=httpx.ConnectError("secreto upstream"))
    monkeypatch.setattr(httpx, "post", remoto)
    monkeypatch.delenv("CLOUD_APP_USUARIO", raising=False)
    monkeypatch.delenv("CLOUD_APP_PASSWORD", raising=False)
    app.dependency_overrides[get_db] = obtener_db
    cliente = TestClient(app, raise_server_exceptions=False)
    yield cliente, sesiones, remoto
    cliente.close()
    app.dependency_overrides.clear()
    motor.dispose()


def test_login_local_sin_cloud_y_me_por_id_con_rol_local(entorno_local):
    cliente, sesiones, remoto = entorno_local
    respuesta = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    datos = jwt.decode(cuerpo["access_token"], JWT_SECRET, algorithms=["HS256"],
                       issuer="rescuesync-local", audience="rescuesync-local-api")
    assert datos["sub"] == "7" and datos["exp"] > datos["iat"]
    assert cuerpo["rol"] == "OPERADOR_MUNICIPAL" and cuerpo["token_type"] == "bearer"
    with sesiones() as db:
        db.get(Usuario, 7).email = "cambio@example.org"
        db.commit()
    me = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {cuerpo['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "cambio@example.org"
    assert "password_hash" not in me.json()
    remoto.assert_not_called()


def test_emision_local_ignora_namespace_cloud_heredado(entorno_local, monkeypatch):
    cliente, _, remoto = entorno_local
    monkeypatch.setenv("JWT_ISSUER", "rescuesync-cloud")
    monkeypatch.setenv("JWT_AUDIENCE", "rescuesync-backend")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "5")
    respuesta = cliente.post("/api/v1/auth/login", json=LOGIN)
    assert respuesta.status_code == 200
    datos = jwt.decode(respuesta.json()["access_token"], JWT_SECRET, algorithms=["HS256"],
                       issuer="rescuesync-local", audience="rescuesync-local-api")
    assert datos["exp"] - datos["iat"] == 300
    remoto.assert_not_called()


def test_registro_hash_local_y_login_sin_cloud(entorno_local):
    cliente, sesiones, remoto = entorno_local
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["rol"] == "OPERADOR_MUNICIPAL"
    with sesiones() as db:
        usuario = db.query(Usuario).filter_by(email=ALTA["email"]).one()
        assert usuario.password_hash != ALTA["password"]
        assert verificar_password(ALTA["password"], usuario.password_hash)
    assert cliente.post("/api/v1/auth/login", json={k: ALTA[k] for k in ("email", "password")}).status_code == 200
    remoto.assert_not_called()


@pytest.mark.parametrize("cambios,estado", [
    ({"email": LOGIN["email"]}, 409), ({"rol_id": 999}, 404),
    ({"rol_id": 2}, 400), ({"organizacion_id": 999}, 404),
    ({"password": "é" * 40}, 400),
])
def test_registro_valida_y_no_persiste_en_error(entorno_local, cambios, estado):
    cliente, sesiones, remoto = entorno_local
    respuesta = cliente.post("/api/v1/auth/registro", json={**ALTA, **cambios})
    assert respuesta.status_code == estado, respuesta.text
    assert "access_token" not in respuesta.json()
    with sesiones() as db:
        assert db.query(Usuario).count() == 1
    remoto.assert_not_called()


@pytest.mark.parametrize("password_hash", ["!cloud", "roto", ""])
def test_hash_invalido_no_es_error_500(entorno_local, password_hash):
    cliente, sesiones, remoto = entorno_local
    with sesiones() as db:
        db.get(Usuario, 7).password_hash = password_hash
        db.commit()
    assert cliente.post("/api/v1/auth/login", json=LOGIN).status_code == 401
    remoto.assert_not_called()


def test_password_erronea_ausente_e_inactivo(entorno_local):
    cliente, sesiones, remoto = entorno_local
    assert cliente.post("/api/v1/auth/login", json={**LOGIN, "password": "incorrecta"}).status_code == 401
    assert cliente.post("/api/v1/auth/login", json={**LOGIN, "email": "ausente@example.org"}).status_code == 401
    with sesiones() as db:
        db.get(Usuario, 7).activo = False
        db.commit()
    assert cliente.post("/api/v1/auth/login", json=LOGIN).status_code == 403
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_local()}"}).status_code == 403
    remoto.assert_not_called()


@pytest.mark.parametrize("cambios", [
    {"sub": ""}, {"sub": True}, {"sub": 7}, {"sub": "7.0"}, {"sub": "-7"},
    {"sub": "0"}, {"sub": "999"}, {"sub": " 7"}, {"sub": "7" * 100},
    {"sub": "2147483648"}, {"sub": "07"}, {"sub": "７"},
    {"exp": 1}, {"exp": True}, {"exp": "9999999999"}, {"exp": None},
    {"iat": int(time.time()) + 3600}, {"iat": True}, {"iss": "otro"}, {"aud": "otro"},
    {"iss": "rescuesync-cloud", "aud": ["rescuesync-backend"], "usuario": LOGIN["email"]},
])
def test_guard_rechaza_claims_invalidos_y_cloud(entorno_local, cambios):
    respuesta = entorno_local[0].get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token_local(**cambios)}"})
    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("claim", ["sub", "iat", "exp", "iss", "aud"])
def test_guard_exige_claims(entorno_local, claim):
    datos = jwt.decode(token_local(), JWT_SECRET, algorithms=["HS256"], audience="rescuesync-local-api")
    del datos[claim]
    token = jwt.encode(datos, JWT_SECRET, algorithm="HS256")
    assert entorno_local[0].get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("algoritmo,secreto", [("HS384", JWT_SECRET), ("HS256", "otro-secreto-de-prueba-con-32-bytes")])
def test_guard_rechaza_algoritmo_y_firma(entorno_local, algoritmo, secreto):
    datos = jwt.decode(token_local(), JWT_SECRET, algorithms=["HS256"], audience="rescuesync-local-api")
    token = jwt.encode(datos, secreto, algorithm=algoritmo)
    assert entorno_local[0].get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_fallo_persistencia_registro_revierte(entorno_local, monkeypatch):
    cliente, sesiones, remoto = entorno_local
    reversiones = []

    def fallar(self, db, usuario):
        revertir = Mock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", revertir)
        reversiones.append(revertir)
        db.add(usuario)
        db.flush()
        raise SQLAlchemyError("secreto persistencia")

    monkeypatch.setattr("app.repositories.UsuarioRepository.crear", fallar)
    respuesta = cliente.post("/api/v1/auth/registro", json=ALTA)
    assert respuesta.status_code == 503 and "secreto" not in respuesta.text
    with sesiones() as db:
        assert db.query(Usuario).count() == 1
    reversiones[0].assert_called_once()
    remoto.assert_not_called()


@pytest.mark.parametrize("ambiente", ["production", "", "development"])
def test_seed_demo_solo_development_idempotente(entorno_local, monkeypatch, ambiente):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", ambiente)
    with sesiones() as db:
        RolService().sembrar_roles(db)
        servicio = AuthService()
        servicio.sembrar_usuarios_iniciales(db)
        servicio.sembrar_usuarios_iniciales(db)
        assert db.query(Usuario).count() == (5 if ambiente == "development" else 1)
        for datos in USUARIOS_INICIALES:
            usuario = db.query(Usuario).filter_by(email=datos["email"]).first()
            if ambiente == "development":
                assert usuario is not None and verificar_password(datos["email"], usuario.password_hash)
            else:
                assert usuario is None
    remoto.assert_not_called()
