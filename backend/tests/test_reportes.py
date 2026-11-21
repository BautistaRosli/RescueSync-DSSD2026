from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Emergencia, EstadoEmergencia, LoteNecesidad, OfertaAyuda, OfertaItem, Organizacion
from app.services.reportes_service import ReportesService


@pytest.fixture
def db():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    sesiones = sessionmaker(motor, expire_on_commit=False)
    with sesiones() as sesion:
        yield sesion
    motor.dispose()


@pytest.fixture
def emergencia(db):
    valor = Emergencia(id=1, nivel_gravedad="alta", zona_afectada="Zona", descripcion_inicial="Descripción",
                       estado=EstadoEmergencia.ESPERA_OFERTAS, publicada=True)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def lote(db, emergencia):
    valor = LoteNecesidad(id=1, emergencia_id=emergencia.id, tipo="agua", cantidad=10)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def oferta(db, emergencia):
    db.add(Organizacion(id=1, nombre="ONG"))
    valor = OfertaAyuda(id=1, emergencia_id=emergencia.id, organizacion_id=1)
    db.add(valor)
    db.commit()
    return valor


@pytest.fixture
def item(db, lote, oferta):
    valor = OfertaItem(id=1, oferta_id=oferta.id, lote_necesidad_id=lote.id, cantidad_ofrecida=1)
    db.add(valor)
    db.commit()
    return valor


def test_reportes_sin_datos_devuelve_ceros_y_listas_vacias(db):
    servicio = ReportesService()
    assert servicio.consorcios(db).model_dump() == {
        "total_ofertas_adjudicadas": 0, "ofertas_conjuntas": 0, "porcentaje_consorcios": 0
    }
    assert servicio.tiempo_publicacion(db).model_dump() == {
        "promedio_horas": 0, "minimo_horas": 0, "maximo_horas": 0
    }


def test_reportes_agrega_oferta_adjudicada_y_cobertura(db, emergencia, lote, oferta, item):
    ahora = datetime.now(timezone.utc)
    emergencia.fecha_publicacion = ahora - timedelta(hours=4)
    emergencia.estado = EstadoEmergencia.RESUELTA
    oferta.adjudicada_en = ahora
    item.cantidad_ofrecida = 7
    item.finalizado_en = ahora
    db.commit()
    servicio = ReportesService()
    assert servicio.cobertura_lotes(db).lotes[0].cantidad_ofrecida == 7
    assert servicio.proyectos(db)[0].items_finalizados == 1
    assert servicio.tiempo_adjudicacion(db).promedio_horas == 4
