"""Aplicación FastAPI del microservicio stateless de prioridad."""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request

from app.priority import calcular_prioridad
from app.schemas import PrioridadRequest, PrioridadResponse

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
NIVEL_LOG = getattr(logging, LOG_LEVEL, logging.INFO)


class FormateadorJson(logging.Formatter):
    """Formatea cada registro de log como una única línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        evento = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for campo in ("method", "path", "status", "duration_ms"):
            if hasattr(record, campo):
                evento[campo] = getattr(record, campo)
        return json.dumps(evento, ensure_ascii=False)


logger = logging.getLogger("prioridad")
if not logger.handlers:
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(FormateadorJson())
    logger.addHandler(manejador)
logger.setLevel(NIVEL_LOG)
logger.propagate = False

# El middleware emite un JSON por request; se evita el access log duplicado.
logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(title="RescueSync Prioridad", version="1.0.0")


@app.middleware("http")
async def registrar_request(request: Request, call_next):
    """Registra método, path, status y duración de cada request."""
    inicio = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": duracion_ms,
            },
        )


@app.get("/health")
def health() -> dict[str, str]:
    """Sonda de vida del proceso."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Sonda de disponibilidad para recibir tráfico."""
    return {"status": "ready"}


@app.post("/prioridad", response_model=PrioridadResponse)
def prioridad(payload: PrioridadRequest) -> PrioridadResponse:
    """Calcula la prioridad de un incidente a partir de gravedad y zona."""
    if not payload.zona.strip():
        raise HTTPException(status_code=400, detail="La zona no puede estar vacía")

    gravedad = payload.gravedad.value
    return PrioridadResponse(
        prioridad=calcular_prioridad(gravedad, payload.zona),
        gravedad=gravedad,
        zona=payload.zona,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level=LOG_LEVEL.lower(),
    )
