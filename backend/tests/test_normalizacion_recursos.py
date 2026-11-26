import httpx
from unittest.mock import Mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Emergencia, LoteNecesidad
from app.services import datos_demo_service
from app.services.recursos_cloud_service import RecursosCloudService
from app.schemas.recursos_cloud_schema import RecursoCloudCrear
from app.utils.recursos import normalizar_nombre_recurso


def respuesta(status, cuerpo):
    return httpx.Response(status, json=cuerpo)


def test_normalizar_nombre_recurso_limpia_espacios_y_mayusculas():
    assert normalizar_nombre_recurso("  mEDICAMENTOS   ") == "Medicamentos"
    assert normalizar_nombre_recurso(" kits   DE alimentos ") == "Kits de alimentos"


def test_crear_recurso_cloud_envia_nombre_normalizado(monkeypatch):
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.obtener_token_aplicacion",
        Mock(return_value="token"),
    )
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.listar_items",
        Mock(return_value=respuesta(200, [])),
    )
    alta = Mock(return_value=respuesta(
        201, {"id": 44, "nombre": "medicamentos", "descripcion": None}
    ))
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.crear_item", alta
    )

    recurso, creado = RecursosCloudService().crear(
        RecursoCloudCrear(nombre="  mEDICAMENTOS  ")
    )

    assert creado is True
    assert recurso.nombre == "Medicamentos"
    assert alta.call_args.args[0] == "Medicamentos"


def test_equivalencias_demo_reales_idempotentes(monkeypatch, tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'demo.sqlite3'}")
    Base.metadata.create_all(motor)
    llamadas = []

    class ServicioCloudFalso:
        def crear(self, data):
            llamadas.append(data.nombre)
            return type("Recurso", (), {"id": 701})(), True

    monkeypatch.setattr(datos_demo_service, "RecursosCloudService", ServicioCloudFalso)
    with Session(motor) as db:
        emergencia = Emergencia(
            nivel_gravedad="ALTA", zona_afectada="Zona Norte",
            descripcion_inicial="[DEMO DASHBOARD] prueba",
            estado="ESPERA_LOTES", prioridad=5, publicada=False,
        )
        emergencia.lotes = [LoteNecesidad(tipo="  mEDICAMENTOS  ", cantidad=2)]
        db.add(emergencia)
        db.flush()

        assert datos_demo_service._resolver_equivalencias_cloud(db, [emergencia])
        db.flush()
        assert emergencia.lotes[0].tipo == "Medicamentos"
        assert emergencia.lotes[0].referencia_cloud.tipo_recurso_id == 701

        assert not datos_demo_service._resolver_equivalencias_cloud(db, [emergencia])
        assert llamadas == ["Medicamentos"]


def test_equivalencias_demo_no_abortan_si_cloud_no_esta_disponible(monkeypatch, tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'demo_cloud_caido.sqlite3'}")
    Base.metadata.create_all(motor)
    estado = {"disponible": False}
    llamadas = []

    class ServicioCloudFalso:
        def crear(self, data):
            if not estado["disponible"]:
                raise HTTPException(503, "Catálogo de recursos Cloud no disponible")
            llamadas.append(data.nombre)
            return type("Recurso", (), {"id": 702})(), True

    monkeypatch.setattr(datos_demo_service, "RecursosCloudService", ServicioCloudFalso)
    with Session(motor) as db:
        emergencia = Emergencia(
            nivel_gravedad="ALTA", zona_afectada="Zona Norte",
            descripcion_inicial="[DEMO DASHBOARD] prueba cloud caído",
            estado="ESPERA_LOTES", prioridad=5, publicada=False,
        )
        emergencia.lotes = [LoteNecesidad(tipo="Medicamentos", cantidad=2)]
        db.add(emergencia)
        db.flush()

        # Cloud no disponible: no propaga la excepción ni marca cambios.
        assert not datos_demo_service._resolver_equivalencias_cloud(db, [emergencia])
        db.flush()
        assert emergencia.lotes[0].referencia_cloud is None
        assert llamadas == []

        # Siguiente arranque con Cloud disponible: resuelve la equivalencia.
        estado["disponible"] = True
        assert datos_demo_service._resolver_equivalencias_cloud(db, [emergencia])
        db.flush()
        assert emergencia.lotes[0].referencia_cloud.tipo_recurso_id == 702
        assert llamadas == ["Medicamentos"]
