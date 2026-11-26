import re
import unicodedata

import httpx
from fastapi import HTTPException

from ..integrations import cloud_client
from ..schemas.recursos_cloud_schema import (
    RecursoCloudCrear,
    RecursoCloudRespuesta,
)
from ..utils.recursos import normalizar_nombre_recurso


class RecursosCloudService:
    """Consulta y administra el catálogo nacional de recursos."""

    def listar(self, texto: str | None = None) -> list[RecursoCloudRespuesta]:
        respuesta = self._solicitar_catalogo()
        recursos = self._validar_lista(respuesta)
        termino = self._normalizar(texto or "")
        if termino:
            recursos = [
                recurso for recurso in recursos
                if termino in self._normalizar(recurso.nombre)
            ]
        return recursos

    def crear(self, data: RecursoCloudCrear) -> tuple[RecursoCloudRespuesta, bool]:
        existentes = self.listar()
        nombre = normalizar_nombre_recurso(data.nombre)
        normalizado = self._normalizar(nombre)
        existente = next(
            (recurso for recurso in existentes
             if self._normalizar(recurso.nombre) == normalizado),
            None,
        )
        if existente is not None:
            return existente, False

        try:
            token = cloud_client.obtener_token_aplicacion()
            respuesta = cloud_client.crear_item(nombre, data.descripcion, token)
        except (
            cloud_client.AutenticacionAplicacionError,
            httpx.RequestError,
            httpx.InvalidURL,
        ):
            raise HTTPException(503, "Catálogo de recursos Cloud no disponible") from None

        if respuesta.status_code == 409:
            # Evita duplicados ante una creación concurrente.
            existente = next(
                (recurso for recurso in self.listar()
                 if self._normalizar(recurso.nombre) == normalizado),
                None,
            )
            if existente is not None:
                return existente, False

        if respuesta.status_code != 201:
            raise HTTPException(
                502,
                f"Cloud respondió con estado {respuesta.status_code}: "
                f"{self._detalle(respuesta)}",
            )
        return self._validar_recurso(respuesta), True

    def _solicitar_catalogo(self) -> httpx.Response:
        try:
            token = cloud_client.obtener_token_aplicacion()
            respuesta = cloud_client.listar_items(token)
        except (
            cloud_client.AutenticacionAplicacionError,
            httpx.RequestError,
            httpx.InvalidURL,
        ):
            raise HTTPException(503, "Catálogo de recursos Cloud no disponible") from None
        if respuesta.status_code != 200:
            raise HTTPException(
                502,
                f"Cloud respondió con estado {respuesta.status_code}: "
                f"{self._detalle(respuesta)}",
            )
        return respuesta

    def _validar_lista(self, respuesta: httpx.Response) -> list[RecursoCloudRespuesta]:
        try:
            datos = respuesta.json()
        except (ValueError, TypeError):
            raise HTTPException(502, "Cloud devolvió un catálogo inválido") from None
        if not isinstance(datos, list):
            raise HTTPException(502, "Cloud devolvió un catálogo inválido")
        try:
            return [self._normalizar_recurso(RecursoCloudRespuesta.model_validate(item)) for item in datos]
        except (TypeError, ValueError):
            raise HTTPException(502, "Cloud devolvió un catálogo inválido") from None

    @staticmethod
    def _validar_recurso(respuesta: httpx.Response) -> RecursoCloudRespuesta:
        try:
            return RecursosCloudService._normalizar_recurso(
                RecursoCloudRespuesta.model_validate(respuesta.json())
            )
        except (TypeError, ValueError):
            raise HTTPException(502, "Cloud devolvió un recurso inválido") from None

    @staticmethod
    def _normalizar(valor: str) -> str:
        valor = unicodedata.normalize("NFKD", valor)
        valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
        return re.sub(r"\s+", " ", valor).strip().casefold()

    @staticmethod
    def _normalizar_recurso(recurso: RecursoCloudRespuesta) -> RecursoCloudRespuesta:
        return recurso.model_copy(update={"nombre": normalizar_nombre_recurso(recurso.nombre)})

    @staticmethod
    def _detalle(respuesta: httpx.Response) -> str:
        try:
            datos = respuesta.json()
        except (ValueError, TypeError):
            datos = None
        if isinstance(datos, dict) and isinstance(datos.get("detail"), str):
            return datos["detail"][:300]
        return (respuesta.text or "sin detalle")[:300]
