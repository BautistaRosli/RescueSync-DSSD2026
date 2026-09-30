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