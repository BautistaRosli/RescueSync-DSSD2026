"""Precarga local con identidades nacionales ficticias y transporte aislado."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.integrations import cloud_client
from app.models import (Emergencia, EstadoEmergencia, LoteNecesidad,
                        LoteRecursoCloud, OfertaAyuda, OfertaItem, Organizacion,
                        OrganizacionCloud, Usuario)
from app.services.solicitud_evaluacion_service import SolicitudEvaluacionService
from app.services.usuarios_service import (AuthService, ORGANIZACION_ONU,
                                          ORGANIZACION_UNICEF, RolService)
from test_concurrencia import sesiones_pg


@pytest.fixture
def sesiones_precarga_pg(sesiones_pg):
    # La fixture original inserta id=1 explícito sin avanzar la secuencia.
    with sesiones_pg() as db:
        db.execute(text("SELECT setval(pg_get_serial_sequence('organizaciones', 'id'), "
                        "(SELECT max(id) FROM organizaciones))"))
        db.commit()
    return sesiones_pg


@pytest.fixture
def precarga(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    for ong in ("ONU", "UNICEF"):
        for campo in ("CUIT", "ONG_ID"):
            monkeypatch.delenv(f"CLOUD_{ong}_{campo}", raising=False)
    monkeypatch.setattr("app.services.usuarios_service.hashear_password", lambda _: "hash-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", Mock(return_value="token-prueba"))
    monkeypatch.setattr(httpx, "post", Mock(side_effect=AssertionError("HTTP no configurado")))
    monkeypatch.setattr(httpx, "get", Mock(side_effect=AssertionError("HTTP no configurado")))
    motor = create_engine(f"sqlite:///{tmp_path / 'precarga.sqlite3'}")
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, autoflush=False)
    with sesiones() as db:
        RolService().sembrar_roles(db)
    yield sesiones
    motor.dispose()


def sembrar(sesiones):
    with sesiones() as db:
        AuthService().sembrar_usuarios_iniciales(db)


def configurar(monkeypatch, ong="ONU", identificador="901"):
    monkeypatch.setenv(f"CLOUD_{ong}_CUIT", f"cuit-ficticio-{ong.lower()}")
    if identificador is not None:
        monkeypatch.setenv(f"CLOUD_{ong}_ONG_ID", identificador)


def ficha(ong="ONU", identificador=901):
    datos = ORGANIZACION_ONU if ong == "ONU" else ORGANIZACION_UNICEF
    return {"id": identificador, "cuit": f"cuit-ficticio-{ong.lower()}",
            "razon_social": datos["nombre"], "email": datos["email"]}


def test_precarga_historica_desbloquea_solicitud_sin_cambiar_ids(precarga, monkeypatch):
    sembrar(precarga)
    with precarga() as db:
        ong = db.query(Organizacion).filter_by(nombre=ORGANIZACION_ONU["nombre"]).one()
        local_id = ong.id
        representante_id = db.query(Usuario).filter_by(email="ong@ong.com").one().id
        emergencia = Emergencia(nivel_gravedad="alta", zona_afectada="Zona de prueba",
                                descripcion_inicial="Prueba", estado=EstadoEmergencia.ESPERA_OFERTAS)
        db.add(emergencia)
        db.flush()
        lote = LoteNecesidad(emergencia_id=emergencia.id, tipo="Agua", cantidad=10)
        oferta = OfertaAyuda(emergencia_id=emergencia.id, organizacion_id=local_id)
        db.add_all([lote, oferta])
        db.flush()
        lote.referencia_cloud = LoteRecursoCloud(tipo_recurso_id=41)
        db.add(OfertaItem(oferta_id=oferta.id, lote_necesidad_id=lote.id, cantidad_ofrecida=5))
        db.commit()
        emergencia_id, oferta_id = emergencia.id, oferta.id
        with pytest.raises(HTTPException) as error:
            SolicitudEvaluacionService().obtener(db, emergencia_id)
        assert error.value.status_code == 409 and "ong_id" in error.value.detail
    configurar(monkeypatch)
    consulta = Mock(return_value=httpx.Response(200, json=ficha()))
    monkeypatch.setattr(httpx, "get", consulta)
    sembrar(precarga)
    with precarga() as db:
        solicitud = SolicitudEvaluacionService().obtener(db, emergencia_id)
        assert solicitud.ofertas[0].ong_responsable_id == 901
        assert solicitud.ofertas[0].oferta_id == oferta_id
        assert db.get(OrganizacionCloud, local_id).ong_id == 901 != local_id
        assert db.get(Usuario, representante_id).organizacion_id == local_id
        assert db.query(Organizacion).count() == 2
    consulta.assert_called_once()


def test_alta_nueva_ambas_ongs_registra_antes_de_vincular_e_idempotencia(precarga, monkeypatch):
    for clave in ("ONU", "UNICEF"):
        configurar(monkeypatch, clave, None)
    ids = {"cuit-ficticio-onu": 901, "cuit-ficticio-unicef": 977}

    def registrar(url, *, json, headers, timeout):
        assert url.endswith("/ongs/registro")
        assert headers == {"Authorization": "Bearer token-prueba"} and timeout == 10
        with precarga() as db:
            ong = db.query(Organizacion).filter_by(nombre=json["razon_social"]).one()
            assert db.get(OrganizacionCloud, ong.id) is None
        return httpx.Response(201, json={"id": ids[json["cuit"]], **json})

    alta = Mock(side_effect=registrar)
    monkeypatch.setattr(httpx, "post", alta)
    sembrar(precarga)
    sembrar(precarga)
    assert alta.call_count == 2
    with precarga() as db:
        assert sorted(ref.ong_id for ref in db.query(OrganizacionCloud)) == [901, 977]
        assert db.query(Organizacion).count() == 2 and db.query(Usuario).count() == 5


@pytest.mark.parametrize("cambios,estado", [
    ({"id": True}, 200), ({"id": 990}, 200), ({"cuit": "otra"}, 200),
    ({"razon_social": "Otra ONG"}, 200), ({"email": "otra@example.test"}, 200),
    ({}, 404), ({}, 503),
])
def test_ficha_no_verificada_no_vincula_ni_registra(precarga, monkeypatch, caplog, cambios, estado):
    configurar(monkeypatch)
    consulta = Mock(return_value=httpx.Response(estado, json={**ficha(), **cambios}))
    monkeypatch.setattr(httpx, "get", consulta)
    sembrar(precarga)
    with precarga() as db:
        assert db.query(OrganizacionCloud).count() == 0 and db.query(Usuario).count() == 5
    httpx.post.assert_not_called()
    assert "CLOUD_ONU_CUIT" in caplog.text and "CLOUD_ONU_ONG_ID" in caplog.text
    assert "cuit-ficticio" not in caplog.text and ORGANIZACION_ONU["email"] not in caplog.text


@pytest.mark.parametrize("identificador", ["0", "-1", "no-numero", "1.5"])
def test_id_invalido_no_hace_http(precarga, monkeypatch, identificador):
    configurar(monkeypatch, identificador=identificador)
    sembrar(precarga)
    httpx.get.assert_not_called()
    httpx.post.assert_not_called()


def test_409_indica_id_y_recupera_por_get_en_siguiente_arranque(precarga, monkeypatch, caplog):
    configurar(monkeypatch, identificador=None)
    alta = Mock(return_value=httpx.Response(409, json={"detail": "secreto remoto"}))
    monkeypatch.setattr(httpx, "post", alta)
    sembrar(precarga)
    assert "CLOUD_ONU_ONG_ID" in caplog.text and "secreto remoto" not in caplog.text
    with precarga() as db:
        assert db.query(OrganizacionCloud).count() == 0
    configurar(monkeypatch)
    monkeypatch.setattr(httpx, "get", Mock(return_value=httpx.Response(200, json=ficha())))
    sembrar(precarga)
    alta.assert_called_once()
    with precarga() as db:
        assert db.query(OrganizacionCloud).one().ong_id == 901


def test_cloud_caido_no_impide_otra_ong_y_se_recupera(precarga, monkeypatch, caplog):
    configurar(monkeypatch)
    configurar(monkeypatch, "UNICEF", "977")

    def consultar(url, **kwargs):
        if url.endswith("/901"):
            raise httpx.ConnectError("secreto transporte")
        return httpx.Response(200, json=ficha("UNICEF", 977))

    monkeypatch.setattr(httpx, "get", Mock(side_effect=consultar))
    sembrar(precarga)
    with precarga() as db:
        assert [ref.ong_id for ref in db.query(OrganizacionCloud)] == [977]
        assert db.query(Usuario).count() == 5
    assert "secreto transporte" not in caplog.text
    consulta = Mock(return_value=httpx.Response(200, json=ficha()))
    monkeypatch.setattr(httpx, "get", consulta)
    sembrar(precarga)
    consulta.assert_called_once()
    with precarga() as db:
        assert db.query(OrganizacionCloud).count() == 2


@pytest.mark.parametrize("entorno", ["production", "test", ""])
def test_fuera_de_development_no_precarga_ni_requiere_cloud(precarga, monkeypatch, entorno):
    monkeypatch.setenv("APP_ENV", entorno)
    configurar(monkeypatch)
    sembrar(precarga)
    cloud_client.obtener_token_aplicacion.assert_not_called()
    with precarga() as db:
        assert db.query(Usuario).count() == 0 and db.query(Organizacion).count() == 0


def test_sin_cuit_o_sin_credenciales_conserva_demo(precarga, monkeypatch):
    sembrar(precarga)
    cloud_client.obtener_token_aplicacion.assert_not_called()
    configurar(monkeypatch)
    cloud_client.obtener_token_aplicacion.side_effect = cloud_client.AutenticacionAplicacionError()
    sembrar(precarga)
    with precarga() as db:
        assert db.query(Usuario).count() == 5 and db.query(OrganizacionCloud).count() == 0
    httpx.get.assert_not_called()
    httpx.post.assert_not_called()


def test_vinculo_previo_no_se_reasigna_ni_se_consulta(precarga, monkeypatch, caplog):
    sembrar(precarga)
    with precarga() as db:
        ong = db.query(Organizacion).filter_by(nombre=ORGANIZACION_ONU["nombre"]).one()
        ong.referencia_cloud = OrganizacionCloud(ong_id=901)
        db.commit()
    configurar(monkeypatch, identificador="999")
    sembrar(precarga)
    assert "CLOUD_ONU_ONG_ID contradice" in caplog.text
    httpx.get.assert_not_called()
    httpx.post.assert_not_called()
    with precarga() as db:
        assert db.query(OrganizacionCloud).one().ong_id == 901


def test_id_ocupado_por_otra_organizacion_no_se_vincula(precarga, monkeypatch, caplog):
    with precarga() as db:
        ajena = Organizacion(nombre="Ajena", referencia_cloud=OrganizacionCloud(ong_id=901))
        db.add(ajena)
        db.commit()
        ajena_id = ajena.id
    configurar(monkeypatch)
    monkeypatch.setattr(httpx, "get", Mock(return_value=httpx.Response(200, json=ficha())))
    sembrar(precarga)
    assert "ocupado" in caplog.text
    with precarga() as db:
        assert db.query(OrganizacionCloud).count() == 1
        assert db.query(OrganizacionCloud).one().organizacion_id == ajena_id


def test_201_y_fallo_local_informa_id_y_permite_reintento_get(precarga, monkeypatch, caplog):
    configurar(monkeypatch, identificador=None)
    monkeypatch.setattr(httpx, "post", Mock(return_value=httpx.Response(201, json=ficha())))
    servicio = AuthService()
    actualizar = servicio._organizaciones.actualizar
    monkeypatch.setattr(servicio._organizaciones, "actualizar", Mock(side_effect=SQLAlchemyError("secreto BD")))
    with precarga() as db:
        servicio.sembrar_usuarios_iniciales(db)
        assert db.query(OrganizacionCloud).count() == 0 and db.query(Usuario).count() == 5
    assert "CLOUD_ONU_ONG_ID=901" in caplog.text and "secreto BD" not in caplog.text
    monkeypatch.setattr(servicio._organizaciones, "actualizar", actualizar)
    configurar(monkeypatch)
    monkeypatch.setattr(httpx, "get", Mock(return_value=httpx.Response(200, json=ficha())))
    with precarga() as db:
        servicio.sembrar_usuarios_iniciales(db)
        assert db.query(OrganizacionCloud).one().ong_id == 901
    httpx.post.assert_called_once()


def test_repara_representante_sin_registrar_ong_ajena(precarga, monkeypatch):
    sembrar(precarga)
    with precarga() as db:
        ajena = Organizacion(nombre="Ajena", email="ajena@example.test")
        db.add(ajena)
        db.flush()
        ajena_id = ajena.id
        db.query(Usuario).filter_by(email="ong@ong.com").one().organizacion_id = ajena_id
        db.commit()
    configurar(monkeypatch, identificador=None)
    alta = Mock(return_value=httpx.Response(201, json=ficha()))
    monkeypatch.setattr(httpx, "post", alta)
    sembrar(precarga)
    assert alta.call_args.kwargs["json"]["razon_social"] == ORGANIZACION_ONU["nombre"]
    with precarga() as db:
        assert db.get(Organizacion, ajena_id).referencia_cloud is None
        assert db.query(Usuario).filter_by(email="ong@ong.com").one().organizacion_id != ajena_id


@pytest.mark.parametrize("caso", ["duplicada", "otro_tipo"])
def test_organizacion_local_ambigua_o_no_ong_no_se_registra(precarga, monkeypatch, caplog, caso):
    with precarga() as db:
        db.add(Organizacion(**ORGANIZACION_ONU))
        if caso == "duplicada":
            db.add(Organizacion(**ORGANIZACION_ONU))
        else:
            db.flush()
            db.query(Organizacion).one().tipo = "municipio"
        db.commit()
    configurar(monkeypatch, identificador=None)
    sembrar(precarga)
    assert "ambigua o de otro tipo" in caplog.text
    httpx.get.assert_not_called()
    httpx.post.assert_not_called()


@pytest.mark.parametrize("cuerpo", [None, {}, {**ficha(), "id": True},
                                     {**ficha(), "email": "otra@example.test"}])
def test_alta_no_confirmada_no_guarda_referencia(precarga, monkeypatch, cuerpo):
    configurar(monkeypatch, identificador=None)
    monkeypatch.setattr(httpx, "post", Mock(return_value=httpx.Response(201, json=cuerpo)))
    sembrar(precarga)
    with precarga() as db:
        assert db.query(OrganizacionCloud).count() == 0 and db.query(Usuario).count() == 5


def test_arranques_simultaneos_pg_no_duplican_locales_ni_altas(sesiones_precarga_pg, monkeypatch):
    sesiones_pg = sesiones_precarga_pg
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr("app.services.usuarios_service.hashear_password", lambda _: "hash-prueba")
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", lambda: "token-prueba")
    for clave in ("ONU", "UNICEF"):
        configurar(monkeypatch, clave, None)
        monkeypatch.delenv(f"CLOUD_{clave}_ONG_ID", raising=False)
    alta = Mock(side_effect=lambda cuit, nombre, email, token: httpx.Response(
        201, json={"id": 901 if cuit.endswith("onu") else 977,
                   "cuit": cuit, "razon_social": nombre, "email": email}))
    monkeypatch.setattr(cloud_client, "registrar_ong", alta)
    with sesiones_pg() as db:
        RolService().sembrar_roles(db)
    inicio = Barrier(2)

    def arrancar(_):
        inicio.wait(timeout=5)
        sembrar(sesiones_pg)

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        list(ejecutor.map(arrancar, range(2)))
    assert alta.call_count == 2
    with sesiones_pg() as db:
        assert db.query(OrganizacionCloud).count() == 2
        assert db.query(Usuario).count() == 5
        for datos in (ORGANIZACION_ONU, ORGANIZACION_UNICEF):
            assert db.query(Organizacion).filter_by(nombre=datos["nombre"]).count() == 1


def test_ongs_paralelas_pg_no_bloquean_http_y_no_comparten_id(sesiones_precarga_pg, monkeypatch):
    sesiones_pg = sesiones_precarga_pg
    for clave in ("ONU", "UNICEF"):
        configurar(monkeypatch, clave, None)
        monkeypatch.delenv(f"CLOUD_{clave}_ONG_ID", raising=False)
    with sesiones_pg() as db:
        db.add_all([Organizacion(**datos) for datos in (ORGANIZACION_ONU, ORGANIZACION_UNICEF)])
        db.commit()
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", lambda: "token-prueba")
    ambas_en_cloud = Barrier(2)

    def registrar(cuit, nombre, email, token):
        ambas_en_cloud.wait(timeout=5)
        return httpx.Response(201, json={"id": 901, "cuit": cuit,
                                        "razon_social": nombre, "email": email})

    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)

    def reconciliar(datos):
        with sesiones_pg() as db:
            AuthService()._sembrar_organizacion(db, datos)

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        list(ejecutor.map(reconciliar, (ORGANIZACION_ONU, ORGANIZACION_UNICEF)))
    with sesiones_pg() as db:
        assert db.query(OrganizacionCloud).count() == 1
        assert db.query(OrganizacionCloud).one().ong_id == 901


def test_copia_de_campos_resuelve_alias_por_nombre_y_tercero_no_usa_unicef(precarga, monkeypatch):
    configurar(monkeypatch)
    configurar(monkeypatch, "UNICEF", "977")
    consulta = Mock(return_value=httpx.Response(200, json=ficha()))
    monkeypatch.setattr(httpx, "get", consulta)
    with precarga() as db:
        servicio = AuthService()
        onu = servicio._sembrar_organizacion(db, dict(ORGANIZACION_ONU))
        assert onu.referencia_cloud.ong_id == 901
        tercero = servicio._sembrar_organizacion(db, {**ORGANIZACION_UNICEF, "nombre": "Tercera ONG"})
        assert tercero.referencia_cloud is None
    consulta.assert_called_once()
