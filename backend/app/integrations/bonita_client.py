"""
Cliente HTTP aislado para hablar con Bonita
Hace login, busca el ID del proceso, crea el caso y setea variables.
Concentra todo el acoplamiento (URL, autenticacion de errores, etc..) en un solo lugar, para que 
services/bonita_service.py y las rutas no dependan de los detalles del REST de Bonita. 
"""

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
        response = await client.post(
            "/loginservice",
            data={
                "username": self.username,
                "password": self.password,
                "redirect": "false",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code not in (200, 204):
            raise BonitaClientError(
                f"Fallo de autenticación en Bonita (HTTP {response.status_code})"
            )
        return {
            "session_id": response.cookies.get("JSESSIONID", ""),
            "api_token": response.cookies.get("X-Bonita-API-Token", ""),
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
        response = await client.get(
            "/API/bpm/process",
            params={"f": f"name={self.process_name}"},
        )
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

    async def create_case(
        self, client: httpx.AsyncClient, process_id: str
    ) -> int:
        response = await client.post(
            "/API/bpm/case", json={"processDefinitionId": process_id}
        )
        if response.status_code != 200:
            raise BonitaClientError(
                f"Error creando caso (HTTP {response.status_code})"
            )
        return int(response.json()["id"])

    async def set_case_variable(
        self,
        client: httpx.AsyncClient,
        case_id: int,
        name: str,
        value: Any,
    ) -> None:
        response = await client.put(
            f"/API/bpm/caseVariable/{case_id}/{name}",
            content=json.dumps(value),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise BonitaClientError(
                f"Error seteando variable '{name}' (HTTP {response.status_code})"
            )

    async def set_case_variables(
        self, case_id: int, variables: dict[str, Any]
    ) -> list[str]:
        async with await self._client() as client:
            await self.login(client)
            set_names = []
            for name, value in variables.items():
                await self.set_case_variable(client, case_id, name, value)
                set_names.append(name)
            return set_names

    async def start_emergency_process(
        self, variables: dict[str, Any]
    ) -> int:
        async with await self._client() as client:
            await self.login(client)
            process_id = await self.get_process_id(client)
            case_id = await self.create_case(client, process_id)
            for name, value in variables.items():
                await self.set_case_variable(client, case_id, name, value)
            return case_id


bonita_client = BonitaClient()