import httpx
import pytest

from app.integrations.bonita.client import BonitaClient, BonitaClientError


class RespuestaFalsa:
    """Respuesta minima de httpx para el doble de test."""

    def __init__(self, status_code=200, text="", cookies=None):
        self.status_code = status_code
        self.text = text
        self.cookies = cookies if cookies is not None else {}


class ClienteHttpFalso:
    """Doble de `httpx.AsyncClient` que registra los PUT de caseVariable.

    El POST de login responde 204 para que `BonitaClient.login` no se
    frene, y los PUT devuelven la respuesta configurada.
    """

    def __init__(self, respuesta_put: RespuestaFalsa):
        self.headers: dict[str, str] = {}
        self.puts: list[tuple[str, dict]] = []
        self._respuesta_put = respuesta_put

    async def __aenter__(self) -> "ClienteHttpFalso":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, **kwargs) -> RespuestaFalsa:
        return RespuestaFalsa(status_code=204)

    async def put(self, url, **kwargs) -> RespuestaFalsa:
        self.puts.append((url, kwargs))
        return self._respuesta_put


def _parchear_cliente(monkeypatch, respuesta_put: RespuestaFalsa):
    """Devuelve el cliente HTTP falso inyectado en un BonitaClient."""
    cliente_http = ClienteHttpFalso(respuesta_put)
    cliente = BonitaClient()

    async def _client():
        return cliente_http

    monkeypatch.setattr(cliente, "_client", _client)
    return cliente, cliente_http


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("valor", "tipo_esperado"),
    [
        (3002, "java.lang.Integer"),
        ("Villa Urquiza", "java.lang.String"),
        (True, "java.lang.Boolean"),
        (1.5, "java.lang.Double"),
    ],
)
async def test_set_case_variables_manda_valor_y_tipo_por_punto(
    monkeypatch, valor, tipo_esperado
):
    """Cada tipo de Python viaja envuelto en {"value":..., "type":...}."""
    cliente, cliente_http = _parchear_cliente(
        monkeypatch, RespuestaFalsa(status_code=200)
    )

    nombres = await cliente.set_case_variables(3002, {"zona_afectada": valor})

    assert nombres == ["zona_afectada"]
    url, kwargs = cliente_http.puts[0]
    assert url == "/API/bpm/caseVariable/3002/zona_afectada"
    assert kwargs["json"] == {"value": valor, "type": tipo_esperado}


@pytest.mark.asyncio
async def test_set_case_variables_usa_string_para_tipos_desconocidos(monkeypatch):
    """Un tipo fuera de la tabla cae en el fallback java.lang.String."""
    cliente, cliente_http = _parchear_cliente(
        monkeypatch, RespuestaFalsa(status_code=200)
    )

    await cliente.set_case_variables(3002, {"lotes_json": ["vache"]})

    _, kwargs = cliente_http.puts[0]
    assert kwargs["json"] == {
        "value": ["vache"],
        "type": "java.lang.String",
    }


@pytest.mark.asyncio
async def test_set_case_variables_devuelve_todos_los_nombres(monkeypatch):
    """El PUT sale una vez por variable y se devuelven los nombres."""
    cliente, cliente_http = _parchear_cliente(
        monkeypatch, RespuestaFalsa(status_code=200)
    )
    variables = {
        "emergencia_id": 7,
        "zona_afectada": "Villa Urquiza",
        "nivel_gravedad": "alta",
    }

    nombres = await cliente.set_case_variables(3002, variables)

    assert nombres == list(variables.keys())
    assert [url for url, _ in cliente_http.puts] == [
        f"/API/bpm/caseVariable/3002/{nombre}" for nombre in variables
    ]


@pytest.mark.asyncio
async def test_set_case_variables_levanta_error_con_status_y_body(monkeypatch):
    """Un != 200 corta el seteo con BonitaClientError y el body del motor."""
    cliente, cliente_http = _parchear_cliente(
        monkeypatch,
        RespuestaFalsa(
            status_code=500,
            text="APIException: Attribute 'type' must be specified",
        ),
    )

    with pytest.raises(BonitaClientError) as exc_info:
        await cliente.set_case_variables(3002, {"zona_afectada": "x"})

    mensaje = str(exc_info.value)
    assert "HTTP 500" in mensaje
    assert "zona_afectada" in mensaje
    assert "Attribute 'type' must be specified" in mensaje
    # Corta en la primera variable fallida: solo un PUT llegó a salir.
    assert len(cliente_http.puts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("contrato", [None, {"seleccionInput": [{"oferta_id": 1, "lote_id": 2}]}])
async def test_ejecutar_tarea_conserva_cuerpo_vacio_y_acepta_contrato(monkeypatch, contrato):
    cliente, cliente_http = _parchear_cliente(monkeypatch, RespuestaFalsa())
    peticiones = []

    async def post(url, **kwargs):
        peticiones.append((url, kwargs))
        return RespuestaFalsa(status_code=204)

    cliente_http.post = post
    if contrato is None:
        await cliente.ejecutar_tarea(99)
    else:
        await cliente.ejecutar_tarea(99, contrato)
    assert peticiones[-1] == ("/API/bpm/userTask/99/execution", {"json": contrato or {}})


@pytest.mark.asyncio
@pytest.mark.parametrize("solo_usuarios", [False, True])
async def test_miembro_actor_conserva_consulta_existente_y_filtra_solo_al_pedirlo(monkeypatch, solo_usuarios):
    peticiones = []

    def transportar(request):
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        peticiones.append(request)
        return httpx.Response(200, json=[{"id": "400", "user_id": "12"}])

    cliente = BonitaClient()

    async def crear_cliente():
        return httpx.AsyncClient(base_url="http://bonita.test", transport=httpx.MockTransport(transportar))

    monkeypatch.setattr(cliente, "_client", crear_cliente)
    if solo_usuarios:
        miembro = await cliente.obtener_miembro_actor(7, solo_usuarios=True)
    else:
        miembro = await cliente.obtener_miembro_actor(7)
    assert miembro["user_id"] == "12"
    esperado = ["actor_id=7", "member_type=user"] if solo_usuarios else ["actor_id=7"]
    assert peticiones[0].url.params.get_list("f") == esperado


@pytest.mark.asyncio
async def test_set_case_variables_levanta_error_de_conexion(monkeypatch):
    """Un fallo de red se traduce al mismo BonitaClientError."""
    cliente = BonitaClient()
    cliente_http = ClienteHttpFalso(RespuestaFalsa(status_code=200))

    async def _client():
        return cliente_http

    monkeypatch.setattr(cliente, "_client", _client)

    async def _put_que_falla(url, **kwargs):
        raise httpx.RequestError("connection refused")

    cliente_http.put = _put_que_falla

    with pytest.raises(BonitaClientError, match="No se pudo conectar a Bonita"):
        await cliente.set_case_variables(3002, {"zona_afectada": "x"})


def nodo_archivado(source_id, caso, nombre, fin, state="completed", tipo="USER_TASK"):
    """Elemento de /API/bpm/archivedFlowNode con el formato real de Bonita."""
    return {
        "id": f"a{source_id}-{state}", "sourceObjectId": str(source_id),
        "caseId": str(caso), "rootCaseId": str(caso), "processId": "17",
        "name": nombre, "displayName": nombre, "type": tipo, "state": state,
        "reached_state_date": fin, "last_update_date": fin, "archivedDate": fin,
    }


async def metricas_con(monkeypatch, nodos, casos_abiertos, casos_cerrados, peticiones=None):
    peticiones = peticiones if peticiones is not None else []

    def transportar(request):
        peticiones.append(request)
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        if request.url.path == "/API/bpm/process":
            return httpx.Response(200, json=[{"id": "17"}])
        if request.url.path == "/API/bpm/archivedFlowNode":
            return httpx.Response(200, json=nodos)
        if request.url.path == "/API/bpm/case":
            return httpx.Response(200, json=casos_abiertos)
        if request.url.path == "/API/bpm/archivedCase":
            return httpx.Response(200, json=casos_cerrados)
        return httpx.Response(404)

    cliente = BonitaClient()

    async def crear_cliente():
        return httpx.AsyncClient(
            base_url="http://bonita.test", transport=httpx.MockTransport(transportar)
        )

    monkeypatch.setattr(cliente, "_client", crear_cliente)
    return await cliente.obtener_metricas_reporte()


def etapa(resultado, nombre):
    return next(e for e in resultado["tiempos_por_etapa"] if e["etapa"] == nombre)


@pytest.mark.asyncio
async def test_obtener_metricas_reporte_consulta_bonita_y_calcula_duraciones(monkeypatch):
    peticiones = []
    nodos = [
        nodo_archivado(1, 1001, "Registrar Emergencia", "2026-01-01 10:00:00.000", tipo="AUTOMATIC_TASK"),
        nodo_archivado(2, 1001, "Generar lotes", "2026-01-01 12:30:00.000"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos,
        [{"id": "1001", "start": "2026-01-01 09:59:00.000"}, {"id": "1002", "start": "2026-01-01 09:00:00.000"}],
        [{"id": "5", "sourceObjectId": "1003", "start": "2026-01-01 08:00:00.000", "end_date": "2026-01-01 09:00:00.000"}],
        peticiones,
    )

    assert resultado["casos"] == {"abiertos": 2, "cerrados": 1}
    assert resultado["convocatorias_camino_alternativo"] == 0
    assert [e["etapa"] for e in resultado["tiempos_por_etapa"]] == [
        "Generar lotes", "Publicar pedido", "Ventana de ofertas", "Seleccionar oferta",
        "Evaluar proyecto", "Marcar actividades finalizadas", "Supervisar proyecto",
    ]
    assert resultado["tiempos_por_etapa"][0] == {
        "etapa": "Generar lotes", "promedio_horas": 2.5, "cantidad": 1
    }
    assert any(
        request.url.path == "/API/bpm/archivedFlowNode"
        and request.url.params.get_list("f") == ["processId=17"]
        and request.url.params["c"] == "2000"
        for request in peticiones
    )
    assert not any(request.url.path == "/API/bpm/archivedHumanTask" for request in peticiones)


@pytest.mark.asyncio
async def test_metricas_duracion_desde_nodo_anterior_del_mismo_caso(monkeypatch):
    nodos = [
        nodo_archivado(3, 1001, "Seleccionar oferta", "2026-01-01 10:03:00.000"),
        nodo_archivado(2, 1001, "Publicar pedido", "2026-01-01 10:00:00.000", tipo="AUTOMATIC_TASK"),
        # Otro caso intercalado no debe afectar al cálculo del caso 1001.
        nodo_archivado(9, 1002, "Generar lotes", "2026-01-01 10:01:00.000"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos,
        [{"id": "1001", "start": "2026-01-01 09:00:00.000"}, {"id": "1002", "start": "2026-01-01 10:00:00.000"}],
        [],
    )

    seleccionar = etapa(resultado, "Seleccionar oferta")
    assert seleccionar["cantidad"] == 1
    assert seleccionar["promedio_horas"] == pytest.approx(0.05)
    assert etapa(resultado, "Publicar pedido")["promedio_horas"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_metricas_ventana_de_ofertas_con_datos_reales_de_bonita(monkeypatch):
    """Datos reales del caso 1: el timer no aparece en archivedFlowNode."""
    nodos = [
        nodo_archivado(4, 1, "Publicar pedido", "2026-11-26 02:23:11.894", tipo="AUTOMATIC_TASK"),
        nodo_archivado(6, 1, "Obtener ofertas locales", "2026-11-26 02:26:13.103",
                       state="executing", tipo="AUTOMATIC_TASK"),
        nodo_archivado(6, 1, "Obtener ofertas locales", "2026-11-26 02:26:13.856",
                       tipo="AUTOMATIC_TASK"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos, [{"id": "1", "start": "2026-11-26 02:20:00.000"}], [],
    )

    ventana = etapa(resultado, "Ventana de ofertas")
    assert ventana["cantidad"] == 1
    assert ventana["promedio_horas"] == pytest.approx(181.209 / 3600)
    assert ventana["promedio_horas"] == pytest.approx(0.0503, abs=1e-4)


@pytest.mark.asyncio
async def test_metricas_ventana_de_ofertas_empareja_cada_ciclo(monkeypatch):
    """Con REABRIR el caso vuelve a Publicar pedido: cada ventana usa la última publicación."""
    nodos = [
        nodo_archivado(4, 1, "Publicar pedido", "2026-01-01 10:00:00.000", tipo="AUTOMATIC_TASK"),
        nodo_archivado(6, 1, "Obtener ofertas locales", "2026-01-01 10:06:00.000", state="ready",
                       tipo="AUTOMATIC_TASK"),
        nodo_archivado(6, 1, "Obtener ofertas locales", "2026-01-01 10:06:01.000", tipo="AUTOMATIC_TASK"),
        nodo_archivado(8, 1, "Evaluar proyecto", "2026-01-01 11:00:00.000"),
        nodo_archivado(14, 1, "Publicar pedido", "2026-01-01 12:00:00.000", tipo="AUTOMATIC_TASK"),
        nodo_archivado(16, 1, "Obtener ofertas locales", "2026-01-01 12:18:00.000", state="executing",
                       tipo="AUTOMATIC_TASK"),
        nodo_archivado(16, 1, "Obtener ofertas locales", "2026-01-01 12:18:05.000", tipo="AUTOMATIC_TASK"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos, [{"id": "1", "start": "2026-01-01 09:00:00.000"}], [],
    )

    ventana = etapa(resultado, "Ventana de ofertas")
    assert ventana["cantidad"] == 2
    # (0.1 h + 0.3 h) / 2
    assert ventana["promedio_horas"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_metricas_primer_nodo_usa_start_del_caso(monkeypatch):
    nodos = [nodo_archivado(2, 1001, "Generar lotes", "2026-01-01T11:30:00")]
    resultado = await metricas_con(
        monkeypatch, nodos, [],
        [{"id": "7", "sourceObjectId": "1001", "start": "2026-01-01 10:00:00.000"}],
    )

    assert etapa(resultado, "Generar lotes") == {
        "etapa": "Generar lotes", "promedio_horas": 1.5, "cantidad": 1
    }


@pytest.mark.asyncio
async def test_metricas_ignora_nodos_no_completados(monkeypatch):
    nodos = [
        nodo_archivado(2, 1001, "Generar lotes", "2026-01-01 11:00:00.000"),
        nodo_archivado(3, 1001, "Seleccionar oferta", "2026-01-01 12:00:00.000", state="aborted"),
        nodo_archivado(4, 1001, "Supervisar proyecto", "fecha-invalida"),
        nodo_archivado(5, 1001, "Marcar actividades finalizadas", "2026-01-01 13:00:00.000"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos, [{"id": "1001", "start": "2026-01-01 10:00:00.000"}], [],
    )

    assert etapa(resultado, "Seleccionar oferta")["cantidad"] == 0
    assert etapa(resultado, "Supervisar proyecto")["cantidad"] == 0
    # El nodo abortado no cuenta como anterior: 11:00 -> 13:00.
    assert etapa(resultado, "Marcar actividades finalizadas")["promedio_horas"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_metricas_camino_alternativo_cuenta_casos_distintos(monkeypatch):
    nodos = [
        nodo_archivado(2, 1001, "Evaluar proyecto", "2026-01-01 11:00:00.000"),
        nodo_archivado(3, 1001, "Evaluar proyecto", "2026-01-01 12:00:00.000"),
        nodo_archivado(4, 1002, "Evaluar proyecto", "2026-01-01 11:00:00.000"),
        nodo_archivado(5, 1003, "Evaluar proyecto", "2026-01-01 11:00:00.000", state="aborted"),
    ]
    resultado = await metricas_con(
        monkeypatch, nodos,
        [{"id": c, "start": "2026-01-01 10:00:00.000"} for c in ("1001", "1002", "1003")], [],
    )

    assert resultado["convocatorias_camino_alternativo"] == 2
    assert etapa(resultado, "Evaluar proyecto")["cantidad"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("cambio,completada", [({}, True), ({"sourceObjectId": "99"}, False),
                                              ({"caseId": "9"}, False), ({"name": "Otra"}, False),
                                              ({"state": "aborted"}, False)])
async def test_tarea_completada_exige_identidad_y_estado_exactos(monkeypatch, cambio, completada):
    peticiones = []

    def transportar(request):
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        peticiones.append(request)
        return httpx.Response(200, json=[{"sourceObjectId": "101", "caseId": "42",
                                         "name": "Generar lotes", "state": "completed", **cambio}])

    cliente = BonitaClient()

    async def crear_cliente():
        return httpx.AsyncClient(
            base_url="http://bonita.test", transport=httpx.MockTransport(transportar)
        )

    monkeypatch.setattr(cliente, "_client", crear_cliente)
    assert await cliente.tarea_completada(42, "101", "Generar lotes") is completada
    assert peticiones[0].url.path == "/API/bpm/archivedHumanTask"
    assert peticiones[0].url.params.get_list("f") == ["sourceObjectId=101", "caseId=42"]


def cliente_de_transporte(monkeypatch, transportar):
    cliente = BonitaClient()

    async def crear_cliente():
        return httpx.AsyncClient(base_url="http://bonita.test", transport=httpx.MockTransport(transportar))

    monkeypatch.setattr(cliente, "_client", crear_cliente)
    return cliente


@pytest.mark.asyncio
async def test_casos_con_tarea_lista_pagina_y_exige_nombre_estado_caso(monkeypatch):
    peticiones = []
    tarea = {"caseId": "42", "name": "Evaluar proyecto", "state": "ready"}

    def transportar(request):
        peticiones.append(request)
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        assert request.url.params.get_list("f") == ["name=Evaluar proyecto", "state=ready"]
        cantidad = int(request.url.params["c"])
        if request.url.params["p"] == "0":
            return httpx.Response(200, json=[tarea] * cantidad)
        return httpx.Response(200, json=[{**tarea, "caseId": "43"}, {**tarea, "state": "completed"},
                                         {**tarea, "name": "Otra"}, {**tarea, "caseId": None},
                                         {**tarea, "caseId": "invalido"}])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    assert await cliente.obtener_casos_con_tarea_lista("Evaluar proyecto") == {"42", "43"}
    assert [r.url.params["p"] for r in peticiones if r.url.path != "/loginservice"] == ["0", "1"]
    assert sum(r.url.path == "/loginservice" for r in peticiones) == 1


@pytest.mark.asyncio
async def test_timer_vigente_vencido_y_reapertura_usan_proxima_ejecucion_y_una_sesion(monkeypatch):
    from datetime import datetime, timezone

    ahora = datetime.now(timezone.utc)
    instante = int(ahora.timestamp() * 1000)
    peticiones = []

    def transportar(request):
        peticiones.append(request)
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        assert request.url.path == "/API/bpm/timerEventTrigger"
        caso = request.url.params["caseId"]
        registros = {
            "41": [{"eventInstanceName": "TImer ofertas", "executionDate": instante + 60000}],
            "42": [{"eventInstanceName": "TImer ofertas", "executionDate": instante - 1}],
            # Una convocatoria reabierta tiene una nueva ejecución, no usa fecha_publicacion.
            "43": [{"eventInstanceName": "TImer ofertas", "executionDate": instante + 120000}],
            "44": [{"eventInstanceName": "Otro timer", "executionDate": instante + 60000}],
            "45": [],
        }
        return httpx.Response(200, json=registros[caso])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    assert await cliente.obtener_casos_con_ofertas_abiertas({"41", "42", "43", "44", "45"}, ahora=ahora) == {"41", "43"}
    assert sum(r.url.path == "/loginservice" for r in peticiones) == 1
    assert {r.url.params["caseId"] for r in peticiones if r.url.path != "/loginservice"} == {"41", "42", "43", "44", "45"}


@pytest.mark.asyncio
@pytest.mark.parametrize("modo", ["tareas", "temporizadores"])
@pytest.mark.parametrize("respuesta", [httpx.Response(500), httpx.Response(200, json={"error": True}),
                                      httpx.Response(200, text="json inválido")])
async def test_consultas_etapa_no_fabrican_resultados_ante_error(monkeypatch, modo, respuesta):
    def transportar(request):
        return httpx.Response(204) if request.url.path == "/loginservice" else respuesta

    cliente = cliente_de_transporte(monkeypatch, transportar)
    with pytest.raises(BonitaClientError):
        if modo == "tareas":
            await cliente.obtener_casos_con_tarea_lista("Evaluar proyecto")
        else:
            await cliente.obtener_casos_con_ofertas_abiertas({"42"})


@pytest.mark.asyncio
async def test_temporizadores_paginan_y_rechazan_fecha_invalida(monkeypatch):
    peticiones = []

    def transportar(request):
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        peticiones.append(request)
        assert request.url.params["caseId"] == "42"
        if request.url.params["p"] == "0":
            return httpx.Response(200, json=[{"eventInstanceName": "Otro"}] * int(request.url.params["c"]))
        return httpx.Response(200, json=[{"eventInstanceName": "TImer ofertas", "executionDate": "invalido"}])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    with pytest.raises(BonitaClientError, match="fecha inválida"):
        await cliente.obtener_casos_con_ofertas_abiertas({"42"})
    assert [r.url.params["p"] for r in peticiones] == ["0", "1"]


@pytest.mark.asyncio
async def test_temporizadores_acotan_concurrencia_y_esperan_lecturas_ante_error(monkeypatch):
    import asyncio

    activas = 0
    maximo = 0
    terminadas = 0
    logins = 0

    async def transportar(request):
        nonlocal activas, maximo, terminadas, logins
        if request.url.path == "/loginservice":
            logins += 1
            return httpx.Response(204)
        activas += 1
        maximo = max(maximo, activas)
        await asyncio.sleep(0)
        activas -= 1
        terminadas += 1
        return httpx.Response(500) if request.url.params["caseId"] == "1" else httpx.Response(200, json=[])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    with pytest.raises(BonitaClientError):
        await cliente.obtener_casos_con_ofertas_abiertas({str(i) for i in range(1, 12)})
    assert 1 < maximo <= 5 and terminadas == 11 and activas == 0 and logins == 1


@pytest.mark.asyncio
async def test_casos_completados_usan_id_original_estado_exacto_y_paginacion(monkeypatch):
    peticiones = []

    def transportar(request):
        peticiones.append(request)
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        assert request.url.path == "/API/bpm/archivedCase"
        assert request.url.params.get_list("f") == ["sourceObjectId=42"]
        if request.url.params["p"] == "0":
            return httpx.Response(200, json=[{"id": "42", "sourceObjectId": "99", "state": "completed"}] * int(request.url.params["c"]))
        return httpx.Response(200, json=[{"id": "999", "sourceObjectId": "42", "state": "completed"}])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    assert await cliente.obtener_casos_completados({"42"}) == {"42"}
    assert [r.url.params["p"] for r in peticiones if r.url.path != "/loginservice"] == ["0", "1"]
    assert sum(r.url.path == "/loginservice" for r in peticiones) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["cancelled", "canceled", "aborted", "aborting", "initializing", "started", "completing", "COMPLETED"])
async def test_casos_archivados_no_completados_no_resuelven(monkeypatch, estado):
    def transportar(request):
        return (httpx.Response(204) if request.url.path == "/loginservice" else
                httpx.Response(200, json=[{"id": "42", "sourceObjectId": "42", "state": estado}]))

    cliente = cliente_de_transporte(monkeypatch, transportar)
    assert await cliente.obtener_casos_completados({"42"}) == set()


@pytest.mark.asyncio
async def test_id_del_archivo_no_se_confunde_con_id_del_caso(monkeypatch):
    def transportar(request):
        return (httpx.Response(204) if request.url.path == "/loginservice" else
                httpx.Response(200, json=[{"id": "42", "sourceObjectId": "99", "state": "completed"}]))

    cliente = cliente_de_transporte(monkeypatch, transportar)
    assert await cliente.obtener_casos_completados({"42"}) == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", [httpx.Response(500), httpx.Response(200, text="inválido"),
    httpx.Response(200, json={}), httpx.Response(200, json=[None]),
    httpx.Response(200, json=[{"id": "42", "state": "completed"}]),
    httpx.Response(200, json=[{"sourceObjectId": "42"}]),
    httpx.Response(200, json=[{"sourceObjectId": None, "state": "completed"}])])
async def test_casos_completados_rechazan_respuestas_invalidas(monkeypatch, respuesta):
    def transportar(request):
        return httpx.Response(204) if request.url.path == "/loginservice" else respuesta

    cliente = cliente_de_transporte(monkeypatch, transportar)
    with pytest.raises(BonitaClientError):
        await cliente.obtener_casos_completados({"42"})


@pytest.mark.asyncio
async def test_casos_completados_acotan_concurrencia_y_esperan_errores(monkeypatch):
    import asyncio

    activas = maximo = terminadas = 0

    async def transportar(request):
        nonlocal activas, maximo, terminadas
        if request.url.path == "/loginservice":
            return httpx.Response(204)
        activas += 1
        maximo = max(maximo, activas)
        await asyncio.sleep(0)
        activas -= 1
        terminadas += 1
        return httpx.Response(500) if request.url.params["f"] == "sourceObjectId=1" else httpx.Response(200, json=[])

    cliente = cliente_de_transporte(monkeypatch, transportar)
    with pytest.raises(BonitaClientError):
        await cliente.obtener_casos_completados({str(i) for i in range(1, 12)})
    assert 1 < maximo <= 5 and terminadas == 11 and activas == 0
