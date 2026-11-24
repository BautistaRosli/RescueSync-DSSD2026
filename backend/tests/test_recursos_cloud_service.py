from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from app.services.recursos_cloud_service import RecursosCloudService
from app.schemas.recursos_cloud_schema import RecursoCloudCrear


def respuesta(status, cuerpo):
    return httpx.Response(status, json=cuerpo)


@pytest.fixture
def servicio(monkeypatch):
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.obtener_token_aplicacion",
        Mock(return_value="token"),
    )
    return RecursosCloudService()


def test_listar_filtra_sin_distinguir_mayusculas_acentos(servicio, monkeypatch):
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.listar_items",
        Mock(return_value=respuesta(200, [
            {"id": 1, "nombre": "Agua Potable", "descripcion": None},
            {"id": 2, "nombre": "Kits de alimentos", "descripcion": "cajas"},
        ])),
    )

    resultado = servicio.listar("agua potable")

    assert [recurso.id for recurso in resultado] == [1]


def test_crear_retorna_existente_y_no_postea_por_nombre_normalizado(servicio, monkeypatch):
    listado = Mock(return_value=respuesta(200, [
        {"id": 7, "nombre": " Agua   Potable ", "descripcion": None},
    ]))
    alta = Mock()
    monkeypatch.setattr("app.services.recursos_cloud_service.cloud_client.listar_items", listado)
    monkeypatch.setattr("app.services.recursos_cloud_service.cloud_client.crear_item", alta)

    recurso, creado = servicio.crear(RecursoCloudCrear(nombre="agua potable"))

    assert (recurso.id, creado) == (7, False)
    alta.assert_not_called()


def test_crear_publica_y_valida_respuesta(servicio, monkeypatch):
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.listar_items",
        Mock(return_value=respuesta(200, [])),
    )
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.crear_item",
        Mock(return_value=respuesta(201, {"id": 8, "nombre": "Agua", "descripcion": None})),
    )

    recurso, creado = servicio.crear(RecursoCloudCrear(nombre=" Agua "))

    assert recurso.id == 8 and creado is True


def test_crear_rechaza_respuesta_invalida(servicio, monkeypatch):
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.listar_items",
        Mock(return_value=respuesta(200, [])),
    )
    monkeypatch.setattr(
        "app.services.recursos_cloud_service.cloud_client.crear_item",
        Mock(return_value=respuesta(201, {"nombre": "Agua"})),
    )

    with pytest.raises(HTTPException) as error:
        servicio.crear(RecursoCloudCrear(nombre="Agua"))
    assert error.value.status_code == 502
