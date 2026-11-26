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
from app.integrations import cloud_client
from app.models import (
    Emergencia,
    EstadoEmergencia,
    OfertaAyuda,
    Organizacion,
    OrganizacionCloud,
    Rol,
    Usuario,
)
from app.services.security_service import JWT_SECRET, hashear_password, verificar_password
from app.services.datos_demo_service import sembrar_datos_demo
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
    registrar = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201,
        json={"id": 900 if cuit == "30-12345678-5" else 901,
              "cuit": cuit, "razon_social": nombre, "email": email},
    ))
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    with sesiones() as db:
        RolService().sembrar_roles(db)
        servicio = AuthService()
        servicio.sembrar_usuarios_iniciales(db)
        servicio.sembrar_usuarios_iniciales(db)
        assert db.query(Usuario).count() == (7 if ambiente == "development" else 1)
        for datos in USUARIOS_INICIALES:
            usuario = db.query(Usuario).filter_by(email=datos["email"]).first()
            if ambiente == "development":
                assert usuario is not None and verificar_password(
                    datos.get("password", datos["email"]), usuario.password_hash
                )
            else:
                assert usuario is None
    remoto.assert_not_called()
    assert registrar.call_count == (2 if ambiente == "development" else 0)


def test_usuario_bonita_se_siembra_y_puede_iniciar_sesion(entorno_local, monkeypatch):
    cliente, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    with sesiones() as db:
        RolService().sembrar_roles(db)
        AuthService().sembrar_usuarios_iniciales(db)
        usuario = db.query(Usuario).filter_by(email="bonita@bonita.com").one()
        assert usuario.rol.nombre == "BONITA"
        assert verificar_password("bonita@bonita.com", usuario.password_hash)

    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={"email": "bonita@bonita.com", "password": "bonita@bonita.com"},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["rol"] == "BONITA"
    remoto.assert_not_called()


def test_seed_repara_organizacion_del_usuario_demo_sin_cambiar_password(
    entorno_local, monkeypatch
):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    registrar = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201,
        json={"id": 900 if cuit == "30-12345678-5" else 901,
              "cuit": cuit, "razon_social": nombre, "email": email},
    ))
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    password_existente = "clave-existente-no-demo"
    with sesiones() as db:
        RolService().sembrar_roles(db)
        rol = db.query(Rol).filter_by(nombre="REPRESENTANTE_ONG").one()
        usuario = Usuario(
            email="unicef@unicef.org",
            nombre="Ana existente",
            apellido="Pérez",
            password_hash=hashear_password(password_existente),
            rol_id=rol.id,
            organizacion_id=None,
            activo=True,
        )
        db.add(usuario)
        db.commit()
        hash_original = usuario.password_hash

        servicio = AuthService()
        servicio.sembrar_usuarios_iniciales(db)
        servicio.sembrar_usuarios_iniciales(db)

        organizacion = db.query(Organizacion).filter_by(nombre="UNICEF").one()
        reparado = db.query(Usuario).filter_by(email="unicef@unicef.org").one()
        assert reparado.organizacion_id == organizacion.id
        assert reparado.password_hash == hash_original
        assert verificar_password(password_existente, reparado.password_hash)
        assert db.query(Organizacion).filter_by(nombre="UNICEF").count() == 1
    remoto.assert_not_called()
    assert registrar.call_count == 2


def test_usuario_unicef_demo_autentica_y_accede_a_sus_rutas(
    entorno_local, monkeypatch
):
    cliente, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    registrar = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201,
        json={"id": 900 if cuit == "30-12345678-5" else 901,
              "cuit": cuit, "razon_social": nombre, "email": email},
    ))
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    with sesiones() as db:
        RolService().sembrar_roles(db)
        AuthService().sembrar_usuarios_iniciales(db)
        monkeypatch.setattr(cloud_client, "listar_items", Mock(return_value=httpx.Response(200, json=[])))
        ids_recursos = {}

        def crear_item(nombre, descripcion, token):
            identificador = ids_recursos.setdefault(nombre, len(ids_recursos) + 41)
            return httpx.Response(201, json={"id": identificador, "nombre": nombre, "descripcion": descripcion})

        monkeypatch.setattr(cloud_client, "crear_item", crear_item)
        sembrar_datos_demo(db)
        representantes = []
        for email in ("ong@ong.com", "unicef@unicef.org"):
            usuario = db.query(Usuario).filter_by(email=email).one()
            assert usuario.rol.nombre == "REPRESENTANTE_ONG"
            assert usuario.organizacion_id is not None
            representantes.append((email, usuario.organizacion_id))
        emergencia_publicada = (
            db.query(Emergencia)
            .filter(
                Emergencia.descripcion_inicial.like("[DEMO DASHBOARD]%"),
                Emergencia.publicada.is_(True),
            )
            .order_by(Emergencia.id.asc())
            .first()
        )
        assert emergencia_publicada is not None
        assert not db.query(OfertaAyuda).join(Emergencia).filter(
            OfertaAyuda.observaciones
            == "Oferta adjudicada de demostración para el dashboard",
            Emergencia.descripcion_inicial.like("[DEMO DASHBOARD]%"),
            Emergencia.publicada.is_(False),
        ).count()

    for email, organizacion_id in representantes:
        login = cliente.post(
            "/api/v1/auth/login",
            json={"email": email, "password": email},
        )
        assert login.status_code == 200, login.text
        encabezados = {"Authorization": f"Bearer {login.json()['access_token']}"}

        ofertas = cliente.get(
            f"/api/v1/ofertas?organizacion_id={organizacion_id}",
            headers=encabezados,
        )
        inventario = cliente.get(
            f"/api/v1/organizaciones/{organizacion_id}/inventario",
            headers=encabezados,
        )
        lotes = cliente.get(
            f"/api/v1/emergencias/{emergencia_publicada.id}/lotes",
            headers=encabezados,
        )
        assert ofertas.status_code != 403, ofertas.text
        assert inventario.status_code != 403, inventario.text
        assert lotes.status_code != 403, lotes.text
    remoto.assert_not_called()
    assert registrar.call_count == 2


def test_seed_ofertas_demo_solo_para_estados_adjudicables(
    entorno_local, monkeypatch
):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    registrar = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201,
        json={"id": 900 if cuit == "30-12345678-5" else 901,
              "cuit": cuit, "razon_social": nombre, "email": email},
    ))
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    with sesiones() as db:
        RolService().sembrar_roles(db)
        AuthService().sembrar_usuarios_iniciales(db)
        monkeypatch.setattr(cloud_client, "listar_items", Mock(return_value=httpx.Response(200, json=[])))
        ids_recursos = {}

        def crear_item(nombre, descripcion, token):
            identificador = ids_recursos.setdefault(nombre, len(ids_recursos) + 41)
            return httpx.Response(201, json={"id": identificador, "nombre": nombre, "descripcion": descripcion})

        monkeypatch.setattr(cloud_client, "crear_item", crear_item)
        sembrar_datos_demo(db)
        emergencias = (
            db.query(Emergencia)
            .filter(Emergencia.descripcion_inicial.like("[DEMO DASHBOARD]%"))
            .order_by(Emergencia.id.asc())
            .all()
        )
        convocatoria_abierta = next(
            emergencia
            for emergencia in emergencias
            if emergencia.publicada
            and emergencia.estado == EstadoEmergencia.ESPERA_OFERTAS
        )
        for emergencia in emergencias:
            ofertas_demo = db.query(OfertaAyuda).filter(
                OfertaAyuda.emergencia_id == emergencia.id,
                OfertaAyuda.observaciones
                == "Oferta adjudicada de demostración para el dashboard",
            ).all()
            if emergencia is convocatoria_abierta:
                assert len(ofertas_demo) == 1
                oferta_abierta = ofertas_demo[0]
                assert oferta_abierta.adjudicada_en is None
                assert oferta_abierta.es_conjunta is False
                assert oferta_abierta.organizacion.nombre == (
                    "Organización de las Naciones Unidas"
                )
                assert oferta_abierta.organizaciones == [oferta_abierta.organizacion]
                assert oferta_abierta.items
                assert all(
                    item.lote_necesidad.emergencia_id == emergencia.id
                    for item in oferta_abierta.items
                )
                continue
            cantidad_ofertas = (
                db.query(OfertaAyuda)
                .filter(
                    OfertaAyuda.emergencia_id == emergencia.id,
                    OfertaAyuda.observaciones
                    == "Oferta adjudicada de demostración para el dashboard",
                )
                .count()
            )
            if emergencia.estado in (
                EstadoEmergencia.EN_PROCESO,
                EstadoEmergencia.RESUELTA,
            ):
                assert len(ofertas_demo) == 1
            else:
                assert cantidad_ofertas == 0
    remoto.assert_not_called()
    assert registrar.call_count == 2


def test_seed_demo_vincula_cloud_y_no_repite_registro(entorno_local, monkeypatch):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    obtener_token = Mock(return_value="token-demo")
    registrar = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201,
        json={"id": 900 if cuit == "30-12345678-5" else 901,
              "cuit": cuit, "razon_social": nombre, "email": email},
    ))
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", obtener_token)
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)

    with sesiones() as db:
        RolService().sembrar_roles(db)
        servicio = AuthService()
        servicio.sembrar_usuarios_iniciales(db)
        vinculaciones = {
            organizacion.nombre: organizacion.referencia_cloud.ong_id
            for organizacion in db.query(Organizacion).all()
            if organizacion.referencia_cloud is not None
        }
        assert vinculaciones == {
            "Organización de las Naciones Unidas": 900,
            "UNICEF": 901,
        }
        assert obtener_token.call_count == 2
        assert registrar.call_count == 2

        servicio.sembrar_usuarios_iniciales(db)
        assert obtener_token.call_count == 2
        assert registrar.call_count == 2
        assert db.query(OrganizacionCloud).count() == 2

    remoto.assert_not_called()


def test_seed_demo_fallo_cloud_no_crea_vinculacion_falsa(entorno_local, monkeypatch):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    registrar = Mock(side_effect=cloud_client.AutenticacionAplicacionError())
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)

    with sesiones() as db:
        RolService().sembrar_roles(db)
        with pytest.raises(RuntimeError, match="Organización de las Naciones Unidas"):
            AuthService().sembrar_usuarios_iniciales(db)
        assert db.query(Organizacion).count() == 0
        assert db.query(OrganizacionCloud).count() == 0

    registrar.assert_called_once()
    remoto.assert_not_called()

    # El próximo arranque reintenta la precarga automática sin duplicar locales.
    registrar.side_effect = lambda cuit, nombre, email, token: httpx.Response(
        201, json={"id": 900 if cuit == "30-12345678-5" else 901,
                   "cuit": cuit, "razon_social": nombre, "email": email})
    with sesiones() as db:
        servicio = AuthService()
        servicio.sembrar_usuarios_iniciales(db)
        servicio.sembrar_usuarios_iniciales(db)
        assert db.query(Organizacion).count() == 2
        assert db.query(OrganizacionCloud).count() == 2
        assert db.query(Usuario).count() == len(USUARIOS_INICIALES) + 1
    assert registrar.call_count == 3


def test_seed_demo_recupera_ong_existente_en_409_y_valida_id(entorno_local, monkeypatch):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    registrar = Mock(side_effect=[
        httpx.Response(409, json={"detail": "El CUIT ya existe", "id": 8}),
        httpx.Response(201, json={
            "id": 901,
            "cuit": "30-87654321-4",
            "razon_social": "UNICEF",
            "email": "unicef@unicef.org",
        }),
    ])
    verificar = Mock(return_value=httpx.Response(200, json={
        "id": 8,
        "cuit": "30-12345678-5",
        "razon_social": "Organización de las Naciones Unidas",
        "email": "ong@onu.org",
    }))
    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    monkeypatch.setattr(cloud_client, "obtener_ong", verificar)

    with sesiones() as db:
        RolService().sembrar_roles(db)
        AuthService().sembrar_usuarios_iniciales(db)
        vinculaciones = {
            organizacion.nombre: organizacion.referencia_cloud.ong_id
            for organizacion in db.query(Organizacion).all()
            if organizacion.referencia_cloud is not None
        }
        assert vinculaciones == {
            "Organización de las Naciones Unidas": 8,
            "UNICEF": 901,
        }

    assert registrar.call_count == 2
    verificar.assert_called_once_with(8, "token-demo")
    remoto.assert_not_called()


def test_seed_demo_409_sin_id_usa_id_configurado_y_lo_valida(entorno_local, monkeypatch):
    _, sesiones, remoto = entorno_local
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CLOUD_APP_USUARIO", "aplicacion-demo-prueba")
    monkeypatch.setenv("CLOUD_APP_PASSWORD", "credencial-demo-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-demo"))
    monkeypatch.setattr(
        cloud_client,
        "registrar_ong",
        Mock(return_value=httpx.Response(409, json={"detail": "El CUIT ya está registrado"})),
    )

    identidades = {
        7: {"id": 7, "cuit": "30-12345678-5", "razon_social": "Organización de las Naciones Unidas", "email": "ong@onu.org"},
        8: {"id": 8, "cuit": "30-87654321-4", "razon_social": "UNICEF", "email": "unicef@unicef.org"},
    }
    verificar = Mock(side_effect=lambda ong_id, token: httpx.Response(200, json=identidades[ong_id]))
    monkeypatch.setattr(cloud_client, "obtener_ong", verificar)

    with sesiones() as db:
        RolService().sembrar_roles(db)
        AuthService().sembrar_usuarios_iniciales(db)
        assert {
            organizacion.nombre: organizacion.referencia_cloud.ong_id
            for organizacion in db.query(Organizacion).all()
        } == {
            "Organización de las Naciones Unidas": 7,
            "UNICEF": 8,
        }

    assert verificar.call_count == 2
    remoto.assert_not_called()
