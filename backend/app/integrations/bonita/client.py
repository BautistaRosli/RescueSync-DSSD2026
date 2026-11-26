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

    # Etapas del dashboard: etiqueta reportada -> nombre del nodo en Bonita.
    # "Ventana de ofertas" no tiene nodo propio: el timer no se archiva en
    # archivedFlowNode, así que se calcula entre dos nodos (ver abajo).
    ETAPAS_REPORTE = {
        "Generar lotes": "Generar lotes",
        "Publicar pedido": "Publicar pedido",
        "Ventana de ofertas": None,
        "Seleccionar oferta": "Seleccionar oferta",
        "Evaluar proyecto": "Evaluar proyecto",
        "Marcar actividades finalizadas": "Marcar actividades finalizadas",
        "Supervisar proyecto": "Supervisar proyecto",
    }
    # Tarea humana donde se decide el camino alternativo (REABRIR/REFORMULAR/...).
    NODO_CAMINO_ALTERNATIVO = "Evaluar proyecto"
    # Ventana de ofertas = inicio de "Obtener ofertas locales" - fin del
    # "Publicar pedido" inmediatamente anterior en el mismo caso.
    ETAPA_VENTANA_OFERTAS = "Ventana de ofertas"
    NODO_FIN_PUBLICACION = "Publicar pedido"
    NODO_INICIO_OFERTAS = "Obtener ofertas locales"
    ESTADOS_TERMINALES = {"completed", "aborted", "skipped", "cancelled"}

    async def obtener_metricas_reporte(self) -> dict[str, Any]:
        """Consulta en Bonita las métricas requeridas por el dashboard.

        Usa archivedFlowNode (incluye tareas de servicio y timers, no solo
        humanas). La duración de cada nodo se mide desde el fin del nodo
        completado anterior del mismo caso (o el inicio del caso) hasta su
        propio fin, porque en el archivo `reached_state_date` es el momento
        en que el nodo llegó a "completed".
        """
        try:
            async with await self._client() as client:
                await self.login(client)
                process_id = await self.get_process_id(client)
                nodos_archivados = await self._obtener_coleccion(
                    client,
                    "/API/bpm/archivedFlowNode",
                    [f"processId={process_id}"],
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

        tiempos_por_etapa, casos_alternativos = self._tiempos_por_etapa(
            nodos_archivados, [*casos_abiertos, *casos_cerrados]
        )
        return {
            "tiempos_por_etapa": tiempos_por_etapa,
            "casos": {
                "abiertos": len(casos_abiertos),
                "cerrados": len(casos_cerrados),
            },
            "convocatorias_camino_alternativo": len(casos_alternativos),
        }

    async def obtener_metricas_casos(self, casos: set[str]) -> dict[str, Any]:
        """Métricas del tablero limitadas a un conjunto de casos originales.

        Por cada caso consulta /case/{id} (activo), /archivedCase por
        sourceObjectId (completed o cancelado, con su end_date) y
        /archivedFlowNode por caseId para los tiempos por etapa.
        Las fechas se devuelven naive, en la hora del servidor Bonita (UTC).
        """
        if not casos:
            return {"casos": {}, "tiempos_por_etapa": self._tiempos_por_etapa([], [])[0],
                    "casos_camino_alternativo": 0}
        limite = asyncio.Semaphore(5)
        try:
            async with await self._client() as client:
                await self.login(client)

                async def consultar(caso_id: str):
                    async with limite:
                        try:
                            respuesta = await client.get(f"/API/bpm/case/{caso_id}")
                        except httpx.RequestError as exc:
                            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")
                        if respuesta.status_code == 200:
                            activo = respuesta.json()
                        elif respuesta.status_code == 404:
                            activo = None
                        else:
                            raise BonitaClientError(
                                f"Error consultando el caso {caso_id} (HTTP {respuesta.status_code})"
                            )
                        archivados = await self._listar_recurso_paginado(
                            client, "archivedCase", {"f": [f"sourceObjectId={caso_id}"]},
                        )
                        nodos = await self._listar_recurso_paginado(
                            client, "archivedFlowNode", {"f": [f"caseId={caso_id}"]},
                        )
                    return caso_id, activo, archivados, nodos

                resultados = await asyncio.gather(*(consultar(caso) for caso in sorted(casos)))
        except httpx.RequestError as exc:
            raise BonitaClientError(f"No se pudo conectar a Bonita: {exc}")

        estados: dict[str, dict[str, Any]] = {}
        registros_casos: list[dict[str, Any]] = []
        todos_los_nodos: list[dict[str, Any]] = []
        for caso_id, activo, archivados, nodos in resultados:
            propios = [a for a in archivados if str(a.get("sourceObjectId")) == caso_id]
            completado = next((a for a in propios if a.get("state") == "completed"), None)
            if completado is not None:
                registro, estado = completado, "completed"
            elif propios:
                registro, estado = propios[0], "cancelado"
            elif isinstance(activo, dict):
                registro, estado = activo, "activo"
            else:
                registro, estado = None, "no_encontrado"
            estados[caso_id] = {
                "estado": estado,
                "inicio": self._parsear_fecha(registro.get("start")) if registro else None,
                "fin": (self._parsear_fecha(registro.get("end_date"))
                        if registro and estado in ("completed", "cancelado") else None),
            }
            if registro is not None:
                registros_casos.append({"id": caso_id, "start": registro.get("start")})
            todos_los_nodos.extend(nodos)
        tiempos_por_etapa, casos_alternativos = self._tiempos_por_etapa(
            todos_los_nodos, registros_casos
        )
        return {
            "casos": estados,
            "tiempos_por_etapa": tiempos_por_etapa,
            "casos_camino_alternativo": len(casos_alternativos & set(casos)),
        }

    @classmethod
    def _tiempos_por_etapa(
        cls, nodos_archivados: list[dict[str, Any]], casos: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """Promedio por etapa del dashboard y casos que pasaron por el camino alternativo."""
        inicio_por_caso: dict[str, datetime] = {}
        for caso in casos:
            inicio = cls._parsear_fecha(caso.get("start"))
            if inicio is None:
                continue
            for clave in ("sourceObjectId", "id"):
                if caso.get(clave) not in (None, ""):
                    inicio_por_caso.setdefault(str(caso[clave]), inicio)

        duraciones = cls._duraciones_por_nodo(nodos_archivados, inicio_por_caso)
        nombre_a_etapa = {
            nodo: etapa for etapa, nodo in cls.ETAPAS_REPORTE.items() if nodo
        }
        etapas: dict[str, list[float]] = {etapa: [] for etapa in cls.ETAPAS_REPORTE}
        casos_alternativos: set[str] = set()
        publicaciones_por_caso: dict[str, list[datetime]] = {}
        obtenciones_por_caso: dict[str, list[datetime]] = {}
        for caso, nombre, horas, fin, inicio_mas_temprano in duraciones:
            if nombre == cls.NODO_CAMINO_ALTERNATIVO:
                casos_alternativos.add(caso)
            if nombre in nombre_a_etapa and horas is not None:
                etapas[nombre_a_etapa[nombre]].append(horas)
            if nombre == cls.NODO_FIN_PUBLICACION:
                publicaciones_por_caso.setdefault(caso, []).append(fin)
            elif nombre == cls.NODO_INICIO_OFERTAS:
                obtenciones_por_caso.setdefault(caso, []).append(inicio_mas_temprano)

        # Cada "Obtener ofertas locales" se empareja con el último "Publicar
        # pedido" completado antes de su inicio (cubre ciclos por REABRIR).
        for caso, inicios in obtenciones_por_caso.items():
            publicaciones = publicaciones_por_caso.get(caso, [])
            for inicio_ofertas in inicios:
                previas = [fin for fin in publicaciones if fin <= inicio_ofertas]
                if previas:
                    etapas[cls.ETAPA_VENTANA_OFERTAS].append(
                        (inicio_ofertas - max(previas)).total_seconds() / 3600
                    )

        return [
            {
                "etapa": etapa,
                "promedio_horas": sum(horas) / len(horas) if horas else 0.0,
                "cantidad": len(horas),
            }
            for etapa, horas in etapas.items()
        ], casos_alternativos

    @classmethod
    def _duraciones_por_nodo(
        cls,
        nodos: list[dict[str, Any]],
        inicio_por_caso: dict[str, datetime],
    ) -> list[tuple[str, str, float | None, datetime, datetime]]:
        """Devuelve (caso, nombre, horas, fin, inicio_mas_temprano) por nodo completado.

        `inicio_mas_temprano` es la reached_state_date más temprana entre todas
        las versiones archivadas del nodo (initializing, ready, executing...).
        """
        # Agrupa las versiones archivadas de un mismo nodo original.
        versiones: dict[str, list[dict[str, Any]]] = {}
        for indice, nodo in enumerate(nodos):
            clave = nodo.get("sourceObjectId") or nodo.get("id") or f"_{indice}"
            versiones.setdefault(str(clave), []).append(nodo)

        completados_por_caso: dict[
            str, list[tuple[datetime, str, datetime | None, datetime]]
        ] = {}
        for grupo in versiones.values():
            completado = next(
                (v for v in grupo if str(v.get("state", "")).lower() == "completed"),
                None,
            )
            if completado is None:
                continue
            fin = cls._parsear_fecha(completado.get("reached_state_date"))
            caso = completado.get("rootCaseId") or completado.get("caseId")
            if fin is None or caso in (None, ""):
                continue
            # Una versión no terminal (p. ej. "ready") marca el inicio real.
            inicio_preferente = None
            for version in grupo:
                if str(version.get("state", "")).lower() in cls.ESTADOS_TERMINALES:
                    continue
                inicio_preferente = cls._parsear_fecha(version.get("reached_state_date"))
                if inicio_preferente is not None:
                    break
            fechas = [cls._parsear_fecha(v.get("reached_state_date")) for v in grupo]
            inicio_mas_temprano = min(f for f in fechas if f is not None)
            completados_por_caso.setdefault(str(caso), []).append(
                (fin, str(completado.get("name", "")), inicio_preferente, inicio_mas_temprano)
            )

        resultado: list[tuple[str, str, float | None, datetime, datetime]] = []
        for caso, completados in completados_por_caso.items():
            completados.sort(key=lambda item: item[0])
            fin_anterior = inicio_por_caso.get(caso)
            for fin, nombre, inicio_preferente, inicio_mas_temprano in completados:
                inicio = inicio_preferente or fin_anterior
                horas = None
                if inicio is not None and fin >= inicio:
                    horas = (fin - inicio).total_seconds() / 3600
                resultado.append((caso, nombre, horas, fin, inicio_mas_temprano))
                fin_anterior = fin
        return resultado

    @staticmethod
    def _parsear_fecha(valor: Any) -> datetime | None:
        """Parsea "YYYY-MM-DD HH:MM:SS.mmm" o ISO; devuelve datetime naive."""
        if not valor:
            return None
        texto = str(valor).strip().replace("Z", "+00:00")
        try:
            fecha = datetime.fromisoformat(texto)
        except ValueError:
            try:
                fecha = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return None
        # Todas las fechas vienen del mismo servidor: se comparan sin zona.
        return fecha.replace(tzinfo=None)

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
