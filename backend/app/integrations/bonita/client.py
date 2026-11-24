import os
from datetime import datetime
from typing import Any
import httpx


class BonitaClientError(Exception):
    pass


class BonitaTaskConflictError(BonitaClientError):
    pass


# Clases Java que espera el motor para cada tipo nativo de Python.
# La clave es el tipo exacto (no una superclase) para que `bool` no caiga
# en `int` y termine guardado como Integer.
TIPOS_JAVA = {
    bool: "java.lang.Boolean",
    int: "java.lang.Integer",
    float: "java.lang.Double",
    str: "java.lang.String",
}

# Fallback seguro: ante un tipo desconocido se manda texto, que el motor
# siempre acepta. Inventar una clase Java nueva seria peor.
TIPO_JAVA_POR_DEFECTO = "java.lang.String"


def tipo_java_de(valor: Any) -> str:
    """Devuelve la clase Java que el motor de Bonita espera para `valor`."""
    return TIPOS_JAVA.get(type(valor), TIPO_JAVA_POR_DEFECTO)


class BonitaClient:
    
    def __init__(self) -> None:
        self.url = os.getenv(
            "BONITA_URL", "http://host.docker.internal:8080/bonita"
        ).rstrip("/")
        self.username = os.getenv("BONITA_USER", "install")
        self.password = os.getenv("BONITA_PASSWORD", "install")
        self.process_name = os.getenv("BONITA_PROCESS_NAME", "RescueSync")

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, timeout=30.0)

    async def login(self, client: httpx.AsyncClient) -> dict[str, str]:
        try:
            response = await client.post(
                "/loginservice",
                data={
                    "username": self.username,
                    "password": self.password,
                    "redirect": "false",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")
        if response.status_code not in (200, 204):
            raise BonitaClientError(
                f"Fallo de autenticación en Bonita (HTTP {response.status_code})"
            )
        api_token = response.cookies.get("X-Bonita-API-Token", "")
        client.headers["X-Bonita-API-Token"] = api_token
        return {
            "session_id": response.cookies.get("JSESSIONID", ""),
            "api_token": api_token,
        }

    async def test_login(self) -> dict:
        try:
            async with await self._client() as client:
                creds = await self.login(client)
                return {
                    "ok": True,
                    "session_active": bool(creds["session_id"]),
                    "has_csrf_token": bool(creds["api_token"]),
                }
        except (httpx.RequestError, BonitaClientError) as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")

    async def get_process_id(self, client: httpx.AsyncClient) -> str:
        try:
            response = await client.get(
                "/API/bpm/process",
                params={"f": f"name={self.process_name}"},
            )
        except httpx.RequestError as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")
        if response.status_code != 200:
            raise BonitaClientError(
                f"Error consultando proceso (HTTP {response.status_code})"
            )
        processes = response.json()
        if not processes:
            raise BonitaClientError(
                f"No se encontró el proceso '{self.process_name}'"
            )
        return str(processes[0]["id"])

    async def obtener_metricas_reporte(self) -> dict[str, Any]:
        """Consulta en Bonita las métricas requeridas por el dashboard."""
        try:
            async with await self._client() as client:
                await self.login(client)
                process_id = await self.get_process_id(client)
                tareas_archivadas = await self._obtener_coleccion(
                    client,
                    "/API/bpm/archivedHumanTask",
                    [f"processId={process_id}"],
                )
                convocatorias_sin_tilde = await self._obtener_coleccion(
                    client,
                    "/API/bpm/archivedHumanTask",
                    [f"processId={process_id}", "name=Decidir curso de accion"],
                )
                convocatorias_con_tilde = await self._obtener_coleccion(
                    client,
                    "/API/bpm/archivedHumanTask",
                    [f"processId={process_id}", "name=Decidir curso de acción"],
                )
                casos_abiertos = await self._obtener_coleccion(
                    client,
                    "/API/bpm/case",
                    [f"processDefinitionId={process_id}"],
                )
                casos_cerrados = await self._obtener_coleccion(
                    client,
                    "/API/bpm/archivedCase",
                    [f"processDefinitionId={process_id}"],
                )
        except httpx.RequestError as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")

        etapas = {
            "Generar lotes": [],
            "Publicar pedido": [],
            "Seleccionar oferta": [],
            "Evaluar proyecto": [],
        }
        convocatorias = len(convocatorias_sin_tilde) + len(convocatorias_con_tilde)
        for tarea in tareas_archivadas:
            nombre = str(tarea.get("name", ""))
            if nombre in etapas:
                inicio = self._fecha_tarea(tarea, "ready")
                fin = self._fecha_tarea(tarea, "completed")
                if inicio is not None and fin is not None and fin >= inicio:
                    etapas[nombre].append((fin - inicio).total_seconds() / 3600)
        return {
            "tiempos_por_etapa": [
                {
                    "etapa": etapa,
                    "promedio_horas": sum(duraciones) / len(duraciones) if duraciones else 0.0,
                    "cantidad": len(duraciones),
                }
                for etapa, duraciones in etapas.items()
            ],
            "casos": {
                "abiertos": len(casos_abiertos),
                "cerrados": len(casos_cerrados),
            },
            "convocatorias_camino_alternativo": convocatorias,
        }

    async def _obtener_coleccion(
        self,
        client: httpx.AsyncClient,
        recurso: str,
        filtros: list[str],
    ) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                recurso,
                params={"p": 0, "c": 2000, "f": filtros},
            )
        except httpx.RequestError as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")
        if response.status_code != 200:
            raise BonitaClientError(
                f"Error consultando {recurso} (HTTP {response.status_code})"
            )
        try:
            datos = response.json()
        except ValueError as exc:
            raise BonitaClientError(f"Respuesta inválida consultando {recurso}") from exc
        if not isinstance(datos, list):
            raise BonitaClientError(f"Respuesta inválida consultando {recurso}")
        return datos

    @staticmethod
    def _fecha_tarea(tarea: dict[str, Any], tipo: str) -> datetime | None:
        nombres = {
            "ready": ("ready_date", "readyDate", "reached_state_date", "reachedStateDate"),
            "completed": (
                "completed_date", "completedDate", "end_date", "endDate",
                "last_update_date", "lastUpdateDate",
            ),
        }[tipo]
        for nombre in nombres:
            valor = tarea.get(nombre)
            if not valor:
                continue
            try:
                return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
            except ValueError:
                continue
        return None

    async def set_case_variables(
        self, case_id: int, variables: dict[str, Any]
    ) -> list[str]:
        """Escribe variables de caso con PUT /API/bpm/caseVariable/{caseId}/{name}.

        El motor exige el envoltorio {"value": ..., "type": ...}: sin `type`
        responde 500 con `Attribute 'type' must be specified`, y mandar el
        valor crudo tampoco sirve. Se hace explicito porque el binding del
        contrato del proceso no deja las variables de caso cargadas.
        """
        async with await self._client() as client:
            await self.login(client)
            set_names = []
            for name, value in variables.items():
                try:
                    response = await client.put(
                        f"/API/bpm/caseVariable/{case_id}/{name}",
                        json={"value": value, "type": tipo_java_de(value)},
                    )
                except httpx.RequestError as exc:
                    raise BonitaClientError(
                        f"No se pudo conectar a Bonita: {exc}"
                    )
                if response.status_code != 200:
                    raise BonitaClientError(
                        f"Error seteando variable '{name}' "
                        f"(HTTP {response.status_code}): {response.text}"
                    )
                set_names.append(name)
            return set_names

    async def start_emergency_process(
        self, variables: dict[str, Any]
    ) -> int:
        async with await self._client() as client:
            await self.login(client)
            process_id = await self.get_process_id(client)
            try:
                response = await client.post(
                    f"/API/bpm/process/{process_id}/instantiation",
                    json=variables,
                )
            except httpx.RequestError as exc:
                raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")
            if response.status_code != 200:
                raise BonitaClientError(
                    f"Error instanciando caso (HTTP {response.status_code}): {response.text}"
                )
            return int(response.json()["caseId"])

    async def obtener_tarea_pendiente(
        self, case_id: int, nombre_tarea: str
    ) -> dict | None:
        """Devuelve la tarea humana pendiente del caso o None si no existe."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.get(
                "/API/bpm/userTask",
                params={"f": [f"caseId={case_id}", f"name={nombre_tarea}"]},
            )
            if response.status_code != 200:
                raise BonitaClientError(
                    f"Error consultando tarea '{nombre_tarea}' "
                    f"(HTTP {response.status_code})"
                )
            tareas = response.json()
            return tareas[0] if tareas else None

    async def obtener_miembro_actor(self, actor_id: int, solo_usuarios: bool = False) -> dict | None:
        """Devuelve el primer usuario miembro del actor Bonita, o None si no tiene."""
        async with await self._client() as client:
            await self.login(client)
            parametros = {"f": f"actor_id={actor_id}"}
            if solo_usuarios:
                parametros = {"p": 0, "c": 1, "f": [f"actor_id={actor_id}", "member_type=user"]}
            response = await client.get(
                "/API/bpm/actorMember",
                params=parametros,
            )
            if response.status_code != 200:
                raise BonitaClientError(
                    f"Error consultando actor {actor_id} "
                    f"(HTTP {response.status_code})"
                )
            miembros = response.json()
            return miembros[0] if miembros else None

    async def obtener_variable_caso(self, case_id: int, nombre: str) -> str | None:
        """Lee el valor textual, incluyendo casos ya archivados por el motor."""
        async with await self._client() as client:
            await self.login(client)
            for recurso in ("caseVariable", "archivedCaseVariable"):
                response = await client.get(f"/API/bpm/{recurso}/{case_id}/{nombre}")
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    raise BonitaClientError(f"Error consultando variable (HTTP {response.status_code})")
                return response.json()["value"]
            return None

    async def asignar_tarea(self, tarea_id: int, usuario_id: int) -> None:
        """Asigna una tarea humana a un usuario del actor (requisito previo para ejecutarla por API)."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.put(
                f"/API/bpm/userTask/{tarea_id}",
                json={"assigned_id": str(usuario_id)},
            )
            if response.status_code not in (200, 204):
                error = BonitaTaskConflictError if response.status_code in (404, 409) else BonitaClientError
                raise error(
                    f"Error asignando tarea {tarea_id} "
                    f"(HTTP {response.status_code}): {response.text}"
                )

    async def ejecutar_tarea(self, tarea_id: int, contrato: dict | None = None) -> None:
        """Ejecuta una tarea humana del caso (barrera de sincronizacion).

        Sin `assign`: la tarea debe estar previamente asignada a un usuario
        del actor, porque el usuario tecnico no puede autoasignarse.
        """
        async with await self._client() as client:
            await self.login(client)
            response = await client.post(
                f"/API/bpm/userTask/{tarea_id}/execution",
                json=contrato if contrato is not None else {},
            )
            if contrato is not None and response.status_code in (400, 404, 409):
                raise BonitaTaskConflictError("Bonita rechazó la ejecución de la tarea")
            if response.status_code not in (200, 204):
                raise BonitaClientError(
                    f"Error ejecutando tarea {tarea_id} "
                    f"(HTTP {response.status_code}): {response.text}"
                )

bonita_client = BonitaClient()
