import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL_POR_DEFECTO = "http://localhost:30080"
TIMEOUT_SEGUNDOS = 3.0
PRIORIDAD_MINIMA = 1
PRIORIDAD_MAXIMA = 10


class PrioridadClientError(Exception):
    """Falla al consultar el microservicio de prioridad."""


class PrioridadClient:
    async def obtener_prioridad(self, gravedad: str, zona: str) -> int:
        """Devuelve la prioridad (1..10) calculada por el microservicio remoto.

        `critica` no existe en el contrato del servicio, que solo acepta
        `alta`, `media` y `baja`: se mapea antes de enviar.
        """
        url = os.getenv("PRIORIDAD_SERVICE_URL", URL_POR_DEFECTO).rstrip("/")


        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as client:
                respuesta = await client.post(
                    f"{url}/prioridad",
                    json={"gravedad": gravedad, "zona": zona},
                )
        except httpx.HTTPError as exc:
            logger.error("Error de conexión con el servicio de prioridad: %s", exc)
            raise PrioridadClientError(
                "No se pudo conectar con el servicio de prioridad"
            ) from exc

        if respuesta.status_code != 200:
            logger.error(
                "El servicio de prioridad respondió HTTP %s",
                respuesta.status_code,
            )
            raise PrioridadClientError(
                "El servicio de prioridad devolvió un estado inesperado"
            )

        try:
            cuerpo: Any = respuesta.json()
        except ValueError as exc:
            logger.error("El servicio de prioridad devolvió un JSON inválido")
            raise PrioridadClientError(
                "El servicio de prioridad devolvió una respuesta inválida"
            ) from exc

        prioridad = cuerpo.get("prioridad") if isinstance(cuerpo, dict) else None
        # `bool` es subclase de `int`: se rechaza explícitamente.
        if (
            isinstance(prioridad, bool)
            or not isinstance(prioridad, int)
            or not PRIORIDAD_MINIMA <= prioridad <= PRIORIDAD_MAXIMA
        ):
            logger.error(
                "El servicio de prioridad devolvió una prioridad inválida"
            )
            raise PrioridadClientError(
                "El servicio de prioridad devolvió una prioridad inválida"
            )

        return prioridad


prioridad_client = PrioridadClient()
