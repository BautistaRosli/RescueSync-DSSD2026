"""Tests del contrato HTTP del servicio de prioridad."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_health_responde_200() -> None:
    """GET /health responde 200 con status ok."""
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


def test_ready_responde_200() -> None:
    """GET /ready responde 200 con status ready."""
    respuesta = cliente.get("/ready")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ready"}


def test_prioridad_valida_contrato() -> None:
    """POST /prioridad válido devuelve entero en [1, 10] y todos los campos."""
    respuesta = cliente.post("/prioridad", json={"gravedad": "alta", "zona": "norte"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"prioridad", "gravedad", "zona", "timestamp"}
    assert isinstance(cuerpo["prioridad"], int)
    assert 1 <= cuerpo["prioridad"] <= 10
    assert cuerpo["gravedad"] == "alta"
    assert cuerpo["zona"] == "norte"
    timestamp = datetime.fromisoformat(cuerpo["timestamp"])
    assert timestamp.tzinfo is not None


def test_gravedad_fuera_de_enum_responde_422() -> None:
    """Una gravedad fuera del enum devuelve 422."""
    respuesta = cliente.post("/prioridad", json={"gravedad": "critica", "zona": "norte"})
    assert respuesta.status_code == 422


def test_campo_faltante_responde_422() -> None:
    """Un payload incompleto devuelve 422."""
    respuesta = cliente.post("/prioridad", json={"gravedad": "alta"})
    assert respuesta.status_code == 422


def test_zona_vacia_responde_400() -> None:
    """Una zona vacía o solo con espacios devuelve 400, no 422."""
    for zona in ("", "   ", "\t\n"):
        respuesta = cliente.post("/prioridad", json={"gravedad": "alta", "zona": zona})
        assert respuesta.status_code == 400
