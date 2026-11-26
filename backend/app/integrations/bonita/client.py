import asyncio
import os
from datetime import datetime, timezone
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

    @staticmethod
    async def _listar_recurso_paginado(
        client: httpx.AsyncClient, recurso: str, parametros: dict,
    ) -> list[dict]:
        """Pagina recursos de lectura y rechaza respuestas incompletas o inválidas."""
        registros = []
        pagina = 0
        por_pagina = 100
        while True:
            try:
                response = await client.get(
                    f"/API/bpm/{recurso}", params={**parametros, "p": pagina, "c": por_pagina},
                )
                if response.status_code != 200:
                    raise BonitaClientError(f"Error consultando {recurso} (HTTP {response.status_code})")
                lote = response.json()
            except (httpx.RequestError, ValueError) as exc:
                raise BonitaClientError(f"No se pudo consultar {recurso} en Bonita") from exc
            if not isinstance(lote, list) or any(not isinstance(fila, dict) for fila in lote):
                raise BonitaClientError(f"Bonita devolvió una lista inválida de {recurso}")
            registros.extend(lote)
            if len(lote) < por_pagina:
                return registros
            pagina += 1

    async def obtener_casos_con_tarea_lista(self, nombre_tarea: str) -> set[str]:
        """Busca todas las tareas ready; vuelve a comprobar los filtros del motor."""
        async with await self._client() as client:
            await self.login(client)
            tareas = await self._listar_recurso_paginado(
                client, "userTask", {"f": [f"name={nombre_tarea}", "state=ready"]},
            )
        return {
            str(tarea["caseId"]) for tarea in tareas
            if tarea.get("name") == nombre_tarea and tarea.get("state") == "ready"
            and str(tarea.get("caseId", "")).isdecimal() and int(tarea["caseId"]) > 0
        }

    async def obtener_casos_completados(self, casos: set[str]) -> set[str]:
        """Consulta archivos por caso original, incluyendo versiones anteriores."""
        if not casos:
            return set()
        limite = asyncio.Semaphore(5)
        async with await self._client() as client:
            await self.login(client)

            async def consultar(caso_id: str) -> tuple[str, list[dict]]:
                async with limite:
                    registros = await self._listar_recurso_paginado(
                        client, "archivedCase", {"f": [f"sourceObjectId={caso_id}"]},
                    )
                return caso_id, registros

            resultados = await asyncio.gather(
                *(consultar(caso) for caso in sorted(casos)), return_exceptions=True,
            )
            for resultado in resultados:
                if isinstance(resultado, BaseException):
                    raise resultado
        completados = set()
        for caso_id, registros in resultados:
            for registro in registros:
                original = registro.get("sourceObjectId")
                estado = registro.get("state")
                if (type(original) not in (str, int) or not str(original).isdecimal()
                        or int(original) <= 0 or not isinstance(estado, str) or not estado):
                    raise BonitaClientError("Bonita devolvió un caso archivado inválido")
                # El id del archivo no identifica al caso municipal original.
                if str(original) == caso_id and estado == "completed":
                    completados.add(caso_id)
        return completados

    async def obtener_casos_con_ofertas_abiertas(
        self, casos: set[str], ahora: datetime | None = None,
    ) -> set[str]:
        """La próxima ejecución del timer determina si la ronda admite ofertas."""
        if not casos:
            return set()
        limite = asyncio.Semaphore(5)
        async with await self._client() as client:
            await self.login(client)

            async def consultar(caso_id: str) -> tuple[str, list[dict]]:
                async with limite:
                    registros = await self._listar_recurso_paginado(
                        client, "timerEventTrigger", {"caseId": caso_id},
                    )
                return caso_id, registros

            # Esperar todas las lecturas antes de cerrar la sesión también si falla una.
            resultados = await asyncio.gather(
                *(consultar(caso_id) for caso_id in sorted(casos)), return_exceptions=True,
            )
            for resultado in resultados:
                if isinstance(resultado, BaseException):
                    raise resultado
        # Medir después de la consulta evita reabrir un timer vencido durante el HTTP.
        instante = (ahora or datetime.now(timezone.utc)).timestamp() * 1000
        abiertos = set()
        for caso_id, registros in resultados:
            for registro in registros:
                if registro.get("eventInstanceName") != "TImer ofertas":
                    continue
                ejecucion = registro.get("executionDate")
                if type(ejecucion) is not int:
                    raise BonitaClientError("Bonita devolvió una fecha inválida del temporizador de ofertas")
                if ejecucion > instante:
                    abiertos.add(caso_id)
        return abiertos

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

    async def tarea_completada(self, case_id: int, tarea_id: str, nombre: str) -> bool:
        """Comprueba una ejecución exacta, sin confundir vueltas del mismo caso."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.get(
                "/API/bpm/archivedHumanTask",
                params={"p": 0, "c": 20, "f": [f"sourceObjectId={tarea_id}", f"caseId={case_id}"]},
            )
            if response.status_code != 200:
                raise BonitaClientError(f"Error consultando tarea archivada (HTTP {response.status_code})")
            return any(str(tarea.get("sourceObjectId")) == str(tarea_id)
                       and str(tarea.get("caseId")) == str(case_id)
                       and tarea.get("name") == nombre and tarea.get("state") == "completed"
                       for tarea in response.json())

    async def tarea_completada_por_nombre(self, case_id: int, nombre: str) -> bool:
        """Comprueba si el caso ya completó una tarea humana por nombre."""
        async with await self._client() as client:
            await self.login(client)
            response = await client.get(
                "/API/bpm/archivedHumanTask",
                params={"p": 0, "c": 50, "f": [f"caseId={case_id}", f"name={nombre}"]},
            )
            if response.status_code != 200:
                raise BonitaClientError(
                    f"Error consultando la tarea archivada '{nombre}' (HTTP {response.status_code})"
                )
            tareas = response.json()
            if not isinstance(tareas, list):
                raise BonitaClientError("Respuesta inválida consultando la tarea archivada")
            return any(
                str(tarea.get("caseId")) == str(case_id)
                and tarea.get("name") == nombre
                and tarea.get("state") == "completed"
                for tarea in tareas
            )

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
