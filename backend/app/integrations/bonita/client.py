import json
import os
from typing import Any
import httpx


class BonitaClientError(Exception):
    pass


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

    async def set_case_variables(
        self, case_id: int, variables: dict[str, Any]
    ) -> list[str]:
        async with await self._client() as client:
            await self.login(client)
            set_names = []
            for name, value in variables.items():
                try:
                    response = await client.put(
                        f"/API/bpm/caseVariable/{case_id}/{name}",
                        content=json.dumps(value),
                        headers={"Content-Type": "application/json"},
                    )
                except httpx.RequestError as exc:
                    raise BonitaClientError(
                        f"No se pudo conectar a Bonita: {exc}"
                    )
                if response.status_code != 200:
                    raise BonitaClientError(
                        f"Error seteando variable '{name}' (HTTP {response.status_code})"
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

    async def obtener_miembro_actor(self, actor_id: int) -> dict | None:
        """Devuelve el primer usuario miembro del actor Bonita, o None si no tiene."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.get(
                "/API/bpm/actorMember",
                params={"f": f"actor_id={actor_id}"},
            )
            if response.status_code != 200:
                raise BonitaClientError(
                    f"Error consultando actor {actor_id} "
                    f"(HTTP {response.status_code})"
                )
            miembros = response.json()
            return miembros[0] if miembros else None

    async def asignar_tarea(self, tarea_id: int, usuario_id: int) -> None:
        """Asigna una tarea humana a un usuario del actor (requisito previo para ejecutarla por API)."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.put(
                f"/API/bpm/userTask/{tarea_id}",
                json={"assigned_id": str(usuario_id)},
            )
            if response.status_code not in (200, 204):
                raise BonitaClientError(
                    f"Error asignando tarea {tarea_id} "
                    f"(HTTP {response.status_code}): {response.text}"
                )

    async def ejecutar_tarea(self, tarea_id: int) -> None:
        """Ejecuta una tarea humana del caso (barrera de sincronizacion).

        Sin `assign`: la tarea debe estar previamente asignada a un usuario
        del actor, porque el usuario tecnico no puede autoasignarse.
        """
        async with await self._client() as client:
            await self.login(client)
            response = await client.post(
                f"/API/bpm/userTask/{tarea_id}/execution",
                json={},
            )
            if response.status_code not in (200, 204):
                raise BonitaClientError(
                    f"Error ejecutando tarea {tarea_id} "
                    f"(HTTP {response.status_code}): {response.text}"
                )

bonita_client = BonitaClient()
