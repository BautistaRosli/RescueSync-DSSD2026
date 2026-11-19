"""Tests unitarios de la lógica pura de prioridad."""

import itertools

import pytest

from app.priority import GRAVEDAD_SCORE, ZONA_SCORE, calcular_prioridad

GRAVEDADES = list(GRAVEDAD_SCORE)
ZONAS = list(ZONA_SCORE)


@pytest.mark.parametrize("gravedad,zona", list(itertools.product(GRAVEDADES, ZONAS)))
def test_prioridad_siempre_en_rango(gravedad: str, zona: str) -> None:
    """Toda combinación gravedad x zona del catálogo cae en [1, 10]."""
    valor = calcular_prioridad(gravedad, zona)
    assert isinstance(valor, int)
    assert 1 <= valor <= 10


def test_alta_norte_mayor_que_baja_centro() -> None:
    """La prioridad relativa respeta gravedad y zona."""
    assert calcular_prioridad("alta", "norte") > calcular_prioridad("baja", "centro")


def test_determinismo() -> None:
    """La misma entrada produce siempre la misma salida."""
    for gravedad, zona in itertools.product(GRAVEDADES, ZONAS):
        assert calcular_prioridad(gravedad, zona) == calcular_prioridad(gravedad, zona)


def test_zona_fuera_de_catalogo_en_rango() -> None:
    """Una zona desconocida también devuelve un valor dentro del rango."""
    valor = calcular_prioridad("media", "zona-desconocida")
    assert 1 <= valor <= 10
