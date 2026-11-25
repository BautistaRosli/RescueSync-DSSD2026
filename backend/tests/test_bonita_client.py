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
        return httpx.AsyncClient(base_url="http://bonita.test", transport=httpx.MockTransport(transportar))

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
