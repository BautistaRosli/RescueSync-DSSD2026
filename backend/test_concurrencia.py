"""Regresiones de concurrencia. TEST_DATABASE_URL habilita PostgreSQL real.

Las pruebas PostgreSQL crean y eliminan únicamente un esquema temporal propio.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Emergencia, LoteNecesidad, OfertaAyuda, Organizacion, Rol, Usuario
from app.repositories import EmergenciaRepository, OfertaRepository
from app.schemas import LoteNecesidadCrear, OfertaActualizar, OfertaCrear, UsuarioCrear
from app.services import AuthService, EmergenciaService, LoteService, OfertaService, RolService
from app.services.usuarios_service import ROLES_INICIALES


@pytest.fixture
def sesiones(tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'concurrencia.sqlite3'}")
    Base.metadata.create_all(motor)
    yield sessionmaker(motor, autoflush=False)
    motor.dispose()


def test_registros_simultaneos_devuelven_conflicto(sesiones, monkeypatch):
    with sesiones() as db:
        db.add(Rol(id=1, nombre="OPERADOR_MUNICIPAL"))
        db.commit()
    barrera = Barrier(2)
    servicio = AuthService()
    obtener = servicio._usuarios.obtener_por_email

    def consultar(db, email):
        usuario = obtener(db, email)
        if usuario is None:
            barrera.wait(timeout=5)
        return usuario

    monkeypatch.setattr(servicio._usuarios, "obtener_por_email", consultar)
    monkeypatch.setattr("app.services.usuarios_service.hashear_password", lambda _: "hash")
    datos = UsuarioCrear(email="igual@ejemplo.com", password="password",
                         nombre="Ana", apellido="Perez", rol_id=1)

    def registrar():
        with sesiones() as db:
            try:
                servicio.registrar_usuario(db, datos)
                return 201
            except HTTPException as exc:
                # El rollback deja la sesión utilizable.
                assert db.query(Usuario).count() == 1
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(lambda _: registrar(), range(2)))
    assert sorted(resultados) == [201, 409]


def test_siembra_simultanea_es_idempotente(sesiones, monkeypatch):
    servicio = RolService()
    barreras = {nombre: Barrier(2) for nombre in ROLES_INICIALES}
    obtener = servicio._repository.obtener_por_nombre

    def consultar(db, nombre):
        rol = obtener(db, nombre)
        if rol is None:
            barreras[nombre].wait(timeout=5)
        return rol

    monkeypatch.setattr(servicio._repository, "obtener_por_nombre", consultar)

    def sembrar(_):
        with sesiones() as db:
            servicio.sembrar_roles(db)

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        list(ejecutor.map(sembrar, range(2)))
    with sesiones() as db:
        assert sorted(rol.nombre for rol in db.query(Rol)) == sorted(ROLES_INICIALES)


@pytest.fixture
def sesiones_pg():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada: requiere PostgreSQL real")
    esquema = f"prueba_concurrencia_{uuid4().hex}"
    administrador = create_engine(url)
    if administrador.dialect.name != "postgresql":
        pytest.fail("TEST_DATABASE_URL debe apuntar a PostgreSQL")
    with administrador.begin() as conexion:
        conexion.execute(text(f'CREATE SCHEMA "{esquema}"'))
    motor = create_engine(url, connect_args={
        "options": f"-csearch_path={esquema} -clock_timeout=5000 -cstatement_timeout=8000"
    })
    try:
        Base.metadata.create_all(motor)
        fabrica = sessionmaker(motor, autoflush=False)
        with fabrica() as db:
            db.add(Emergencia(id=1, nivel_gravedad="alta", zona_afectada="Zona",
                              descripcion_inicial="Prueba"))
            db.add(Organizacion(id=1, nombre="ONG"))
            db.flush()
            db.add_all([LoteNecesidad(id=n, emergencia_id=1, tipo="Agua", cantidad=10)
                        for n in (1, 2)])
            db.add(OfertaAyuda(id=1, emergencia_id=1, organizacion_id=1))
            db.commit()
        yield fabrica
    finally:
        motor.dispose()
        with administrador.begin() as conexion:
            conexion.execute(text(f'DROP SCHEMA "{esquema}" CASCADE'))
        administrador.dispose()


def test_publicacion_impide_escritura_que_leyo_estado_anterior(sesiones_pg):
    leida = Event()
    continuar = Event()

    def crear_lote():
        with sesiones_pg() as db:
            # Conservar la entidad en el identity map reproduce una lectura vieja.
            anterior = EmergenciaRepository().obtener_por_id(db, 1)
            assert not anterior.publicada
            leida.set()
            assert continuar.wait(5)
            with pytest.raises(HTTPException) as error:
                LoteService().crear_lote(db, 1, LoteNecesidadCrear(tipo="Agua", cantidad=1))
            assert error.value.status_code == 409

    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        pendiente = ejecutor.submit(crear_lote)
        assert leida.wait(5)
        with sesiones_pg() as db:
            EmergenciaService().publicar_emergencia(db, 1)
        continuar.set()
        pendiente.result(timeout=10)


def test_publicacion_espera_una_escritura_de_lotes_ya_validada(sesiones_pg, monkeypatch):
    validada = Event()
    publicar_iniciado = Event()
    permitir_commit = Event()
    lotes = LoteService()
    emergencias = EmergenciaService()
    crear = lotes._repository.crear
    obtener = emergencias._repository.obtener_por_id

    def crear_pausado(db, lote):
        # El service ya comprobó publicada=False, todavía no guardó el lote.
        validada.set()
        assert permitir_commit.wait(5)
        return crear(db, lote)

    def obtener_publicacion(*args, **kwargs):
        publicar_iniciado.set()
        return obtener(*args, **kwargs)

    monkeypatch.setattr(lotes._repository, "crear", crear_pausado)
    monkeypatch.setattr(emergencias._repository, "obtener_por_id", obtener_publicacion)

    def agregar():
        with sesiones_pg() as db:
            return lotes.crear_lote(db, 1, LoteNecesidadCrear(tipo="Agua", cantidad=3))

    def publicar():
        with sesiones_pg() as db:
            return emergencias.publicar_emergencia(db, 1)

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        escritura = ejecutor.submit(agregar)
        assert validada.wait(5)
        publicacion = ejecutor.submit(publicar)
        try:
            assert publicar_iniciado.wait(5)
            with pytest.raises(TimeoutError):
                publicacion.result(timeout=0.2)
        finally:
            permitir_commit.set()
        assert escritura.result(timeout=10).cantidad == 3
        assert publicacion.result(timeout=10).publicada
    with sesiones_pg() as db:
        assert db.query(LoteNecesidad).count() == 3


def test_oferta_no_usa_lote_eliminado_desde_lectura_anterior(sesiones_pg):
    with sesiones_pg() as db:
        anterior = EmergenciaRepository().obtener_por_id(db, 1)
        assert len(anterior.lotes) == 2
        with sesiones_pg() as otra:
            LoteService().eliminar_lote(otra, 1)
        with pytest.raises(HTTPException) as error:
            OfertaService().crear_oferta(db, OfertaCrear(
                emergencia_id=1, organizacion_id=1,
                items=[{"lote_necesidad_id": 1, "cantidad_ofrecida": 1}]))
        assert error.value.status_code == 400


def test_reemplazo_de_oferta_no_mezcla_items_de_dos_peticionarios(sesiones_pg):
    with sesiones_pg() as db:
        anterior = OfertaRepository().obtener_por_id(db, 1)
        assert anterior.items == []
        with sesiones_pg() as otra:
            OfertaService().actualizar_oferta(otra, 1, OfertaActualizar(
                items=[{"lote_necesidad_id": 1, "cantidad_ofrecida": 1}]))
        OfertaService().actualizar_oferta(db, 1, OfertaActualizar(
            items=[{"lote_necesidad_id": 2, "cantidad_ofrecida": 2}]))
        assert [item.lote_necesidad_id for item in anterior.items] == [2]


def test_inicio_bonita_simultaneo_crea_un_solo_caso(sesiones_pg, monkeypatch):
    llamadas = []

    async def iniciar(_):
        llamadas.append(1)
        # Permite que la segunda petición alcance el bloqueo de fila.
        await asyncio.sleep(0.2)
        return 42

    monkeypatch.setattr("app.services.emergencias_service.bonita_client.start_emergency_process", iniciar)

    async def solicitar():
        with sesiones_pg() as db:
            return await EmergenciaService().iniciar_proceso_bonita(db, 1)

    async def ejecutar():
        return await asyncio.wait_for(asyncio.gather(solicitar(), solicitar()), timeout=10)

    assert asyncio.run(ejecutar()) == [42, 42]
    assert len(llamadas) == 1
