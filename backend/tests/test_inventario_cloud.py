"""Sincronización del inventario local con el inventario nacional (Cloud simulado)."""

import httpx
import pytest

from app.integrations import cloud_client
from app.models import OrganizacionCloud, RecursoInventario, RecursoInventarioCloud
from app.services.permisos_service import ONG
from test_permisos_api import cabecera, entorno  # noqa: F401  (fixture)

ONG_ID = 7
CATALOGO = [
    {"id": 5, "nombre": "Agua potable", "descripcion": None},
    {"id": 6, "nombre": "Mantas", "descripcion": None},
]
NOMBRES = {item["id"]: item["nombre"] for item in CATALOGO}
RUTA = "/api/v1/organizaciones/1/inventario"
MENSAJE_YA_EXISTE = (
    "El recurso ya existe en el inventario nacional. "
    "Actualizá el inventario y editalo desde el botón Editar."
)


class CloudSimulado:
    """Inventario nacional en memoria con registro de llamadas."""

    def __init__(self):
        self.inventario: dict[tuple[int, int], int] = {}
        self.comprometido: dict[tuple[int, int], int] = {}
        self.caido = False
        self.llamadas: list[tuple] = []

    def _verificar(self):
        if self.caido:
            raise httpx.ConnectError("Cloud caído")

    def listar_items(self, token):
        self._verificar()
        return httpx.Response(200, json=CATALOGO)

    def asignar_item_ong(self, ong_id, item_id, cantidad, token):
        self._verificar()
        self.llamadas.append(("POST", ong_id, item_id, cantidad))
        if (ong_id, item_id) in self.inventario:
            return httpx.Response(409, json={"detail": "El item ya está en el inventario de esta ONG"})
        self.inventario[(ong_id, item_id)] = cantidad
        return httpx.Response(201, json={"ong_id": ong_id, "item_id": item_id, "cantidad": cantidad})

    def actualizar_item_ong(self, ong_id, item_id, cantidad, token):
        self._verificar()
        self.llamadas.append(("PATCH", ong_id, item_id, cantidad))
        if (ong_id, item_id) not in self.inventario:
            return httpx.Response(404, json={"detail": "El item no está en el inventario de esta ONG"})
        self.inventario[(ong_id, item_id)] = cantidad
        return httpx.Response(200, json={"ong_id": ong_id, "item_id": item_id, "cantidad": cantidad})

    def eliminar_item_ong(self, ong_id, item_id, token):
        self._verificar()
        self.llamadas.append(("DELETE", ong_id, item_id))
        if self.inventario.pop((ong_id, item_id), None) is None:
            return httpx.Response(404, json={"detail": "El item no está en el inventario de esta ONG"})
        return httpx.Response(204)

    def disponibilidad_ong(self, ong_id, token):
        self._verificar()
        self.llamadas.append(("DISPONIBILIDAD", ong_id))
        filas = []
        for (ong, item), total in sorted(self.inventario.items()):
            if ong != ong_id:
                continue
            comprometido = self.comprometido.get((ong, item), 0)
            filas.append({"tipo_recurso_id": item, "nombre": NOMBRES.get(item),
                          "unidad": None, "total": total, "comprometido": comprometido,
                          "disponible": max(total - comprometido, 0)})
        return httpx.Response(200, json={"disponibles": filas, "mensaje": None})

    def escrituras(self):
        return [llamada for llamada in self.llamadas if llamada[0] != "DISPONIBILIDAD"]


@pytest.fixture
def cloud(entorno, monkeypatch):  # noqa: F811
    cliente, sesiones, _ = entorno
    simulado = CloudSimulado()
    monkeypatch.setattr(cloud_client, "obtener_token_aplicacion", lambda: "token-app")
    for nombre in ("listar_items", "asignar_item_ong", "actualizar_item_ong",
                   "eliminar_item_ong", "disponibilidad_ong"):
        monkeypatch.setattr(cloud_client, nombre, getattr(simulado, nombre))
    with sesiones() as db:
        db.add(OrganizacionCloud(organizacion_id=1, ong_id=ONG_ID))
        db.commit()
    return cliente, sesiones, simulado


def _vinculado(sesiones, cantidad=10, tipo_recurso_id=5):
    """Crea un recurso local ya vinculado y presente en el Cloud simulado."""
    with sesiones() as db:
        recurso = RecursoInventario(organizacion_id=1, tipo="Agua potable", cantidad_total=cantidad)
        recurso.referencia_cloud = RecursoInventarioCloud(tipo_recurso_id=tipo_recurso_id)
        db.add(recurso)
        db.commit()
        return recurso.id


def test_alta_publica_en_cloud_y_guarda_referencia(cloud):
    cliente, sesiones, simulado = cloud
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 12, "unidad": "litros"},
                             headers=cabecera(ONG))
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "Agua potable" and cuerpo["tipo_recurso_id"] == 5
    assert cuerpo["sincronizado"] is True and cuerpo["comprometido"] == 0 and cuerpo["disponible"] == 12
    assert simulado.escrituras() == [("POST", ONG_ID, 5, 12)]
    with sesiones() as db:
        recurso = db.get(RecursoInventario, cuerpo["id"])
        assert recurso.cantidad_total == 12
        assert recurso.referencia_cloud.tipo_recurso_id == 5


def test_alta_con_item_ya_en_cloud_409_sin_escrituras(cloud):
    cliente, sesiones, simulado = cloud
    simulado.inventario[(ONG_ID, 5)] = 3
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_YA_EXISTE
    # Ni POST ni PATCH: el stock nacional queda intacto.
    assert simulado.escrituras() == []
    assert simulado.inventario == {(ONG_ID, 5): 3}
    with sesiones() as db:
        assert db.query(RecursoInventarioCloud).count() == 0


def test_alta_sin_vinculo_nacional_409(cloud):
    cliente, sesiones, simulado = cloud
    with sesiones() as db:
        db.delete(db.get(OrganizacionCloud, 1))
        db.commit()
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "La ONG no está vinculada al Sistema Nacional"
    assert simulado.escrituras() == []


def test_alta_recurso_inexistente_en_catalogo_404(cloud):
    cliente, _, simulado = cloud
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 99, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Recurso nacional no encontrado"
    assert simulado.escrituras() == []


def test_alta_duplicada_409(cloud):
    cliente, sesiones, simulado = cloud
    _vinculado(sesiones)
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert simulado.escrituras() == []


def test_alta_con_cloud_caido_503_sin_fila_local(cloud):
    cliente, sesiones, simulado = cloud
    simulado.caido = True
    with sesiones() as db:
        antes = db.query(RecursoInventario).count()
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == "No se pudo sincronizar con el Sistema Nacional"
    with sesiones() as db:
        assert db.query(RecursoInventario).count() == antes
        assert db.query(RecursoInventarioCloud).count() == 0


def test_alta_compensa_en_cloud_si_falla_la_base(cloud, monkeypatch):
    cliente, sesiones, simulado = cloud
    from app.api.routes.inventario_api import servicio_inventario

    def fallar(db, recurso):
        raise RuntimeError("base caída")

    monkeypatch.setattr(servicio_inventario._repository, "crear", fallar)
    with pytest.raises(RuntimeError):
        cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert simulado.escrituras() == [("POST", ONG_ID, 5, 8), ("DELETE", ONG_ID, 5)]
    assert simulado.inventario == {}


def test_alta_con_item_existente_409_no_escribe_ni_crea_local(cloud, monkeypatch):
    cliente, sesiones, simulado = cloud
    from app.api.routes.inventario_api import servicio_inventario

    simulado.inventario[(ONG_ID, 5)] = 3

    def fallar(db, recurso):
        raise RuntimeError("base caída")

    # Aunque la base fallara, el alta ni siquiera llega a escribir.
    monkeypatch.setattr(servicio_inventario._repository, "crear", fallar)
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_YA_EXISTE
    assert simulado.escrituras() == []
    assert simulado.inventario == {(ONG_ID, 5): 3}
    with sesiones() as db:
        assert db.query(RecursoInventario).count() == 1
        assert db.query(RecursoInventarioCloud).count() == 0


def test_carrera_de_alta_409_sin_patch(cloud, monkeypatch):
    cliente, sesiones, simulado = cloud
    simulado.inventario[(ONG_ID, 5)] = 3
    # El pre-chequeo no ve el ítem, pero el POST lo encuentra creado.
    monkeypatch.setattr(cloud_client, "disponibilidad_ong", lambda ong_id, token: httpx.Response(
        200, json={"disponibles": []}))
    respuesta = cliente.post(RUTA, json={"tipo_recurso_id": 5, "cantidad_total": 8}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_YA_EXISTE
    assert [e for e in simulado.escrituras() if e[0] == "PATCH"] == []
    assert simulado.inventario == {(ONG_ID, 5): 3}
    with sesiones() as db:
        assert db.query(RecursoInventarioCloud).count() == 0


def test_vinculacion_adapta_total_de_cloud_sin_escrituras(cloud):
    cliente, sesiones, simulado = cloud
    simulado.inventario[(ONG_ID, 6)] = 11

    respuesta = cliente.patch(f"{RUTA}/1", json={"cantidad_total": 4, "tipo_recurso_id": 6},
                              headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "Mantas" and cuerpo["tipo_recurso_id"] == 6
    # Se adopta el total nacional en vez de pisarlo con la cantidad local.
    assert cuerpo["cantidad_total"] == 11
    assert simulado.escrituras() == []
    assert simulado.inventario == {(ONG_ID, 6): 11}
    with sesiones() as db:
        recurso = db.get(RecursoInventario, 1)
        assert recurso.cantidad_total == 11
        assert recurso.referencia_cloud.tipo_recurso_id == 6


def test_edicion_por_debajo_del_comprometido_409(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones, cantidad=10)
    simulado.inventario[(ONG_ID, 5)] = 10
    simulado.comprometido[(ONG_ID, 5)] = 6
    respuesta = cliente.patch(f"{RUTA}/{recurso_id}", json={"cantidad_total": 5}, headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert "(6)" in respuesta.json()["detail"]
    assert simulado.escrituras() == []
    with sesiones() as db:
        assert db.get(RecursoInventario, recurso_id).cantidad_total == 10


def test_edicion_ok_hace_patch(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones, cantidad=10)
    simulado.inventario[(ONG_ID, 5)] = 10
    simulado.comprometido[(ONG_ID, 5)] = 6
    respuesta = cliente.patch(f"{RUTA}/{recurso_id}", json={"cantidad_total": 7}, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["cantidad_total"] == 7 and cuerpo["comprometido"] == 6 and cuerpo["disponible"] == 1
    assert simulado.escrituras() == [("PATCH", ONG_ID, 5, 7)]
    with sesiones() as db:
        assert db.get(RecursoInventario, recurso_id).cantidad_total == 7


def test_edicion_vincula_fila_previa(cloud):
    cliente, sesiones, simulado = cloud
    # El recurso 1 del entorno es una fila vieja sin equivalencia nacional.
    respuesta = cliente.patch(f"{RUTA}/1", json={"cantidad_total": 4, "tipo_recurso_id": 6},
                              headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tipo"] == "Mantas" and respuesta.json()["tipo_recurso_id"] == 6
    assert simulado.escrituras() == [("POST", ONG_ID, 6, 4)]


def test_edicion_fila_previa_sin_tipo_solo_local(cloud):
    cliente, sesiones, simulado = cloud
    respuesta = cliente.patch(f"{RUTA}/1", json={"cantidad_total": 4}, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["sincronizado"] is False
    assert simulado.llamadas == []


def test_baja_con_comprometido_409(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones)
    simulado.inventario[(ONG_ID, 5)] = 10
    simulado.comprometido[(ONG_ID, 5)] = 2
    respuesta = cliente.delete(f"{RUTA}/{recurso_id}", headers=cabecera(ONG))
    assert respuesta.status_code == 409
    assert simulado.escrituras() == []
    with sesiones() as db:
        assert db.get(RecursoInventario, recurso_id) is not None


def test_baja_ok_hace_delete(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones)
    simulado.inventario[(ONG_ID, 5)] = 10
    respuesta = cliente.delete(f"{RUTA}/{recurso_id}", headers=cabecera(ONG))
    assert respuesta.status_code == 204
    assert simulado.escrituras() == [("DELETE", ONG_ID, 5)]
    with sesiones() as db:
        assert db.get(RecursoInventario, recurso_id) is None
        assert db.get(RecursoInventarioCloud, recurso_id) is None


def test_listado_con_cloud(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones)
    simulado.inventario[(ONG_ID, 5)] = 10
    simulado.comprometido[(ONG_ID, 5)] = 4
    respuesta = cliente.get(RUTA, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    filas = {fila["id"]: fila for fila in respuesta.json()}
    assert filas[recurso_id]["tipo_recurso_id"] == 5
    assert filas[recurso_id]["comprometido"] == 4 and filas[recurso_id]["disponible"] == 6
    assert filas[recurso_id]["sincronizado"] is True
    assert filas[1]["tipo_recurso_id"] is None and filas[1]["sincronizado"] is False
    assert simulado.llamadas == [("DISPONIBILIDAD", ONG_ID)]


def test_listado_importa_item_que_solo_existe_en_cloud(cloud):
    cliente, sesiones, simulado = cloud
    simulado.inventario[(ONG_ID, 6)] = 9
    respuesta = cliente.get(RUTA, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    importada = next(f for f in respuesta.json() if f["tipo_recurso_id"] == 6)
    assert importada["tipo"] == "Mantas"
    assert importada["cantidad_total"] == 9
    assert importada["comprometido"] == 0 and importada["disponible"] == 9
    assert importada["sincronizado"] is True
    with sesiones() as db:
        recurso = db.get(RecursoInventario, importada["id"])
        assert recurso.referencia_cloud.tipo_recurso_id == 6
        assert recurso.cantidad_total == 9


def test_listado_actualiza_total_local_desde_cloud(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones, cantidad=10)
    simulado.inventario[(ONG_ID, 5)] = 14
    respuesta = cliente.get(RUTA, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    fila = next(f for f in respuesta.json() if f["id"] == recurso_id)
    assert fila["cantidad_total"] == 14
    assert fila["sincronizado"] is True
    with sesiones() as db:
        assert db.get(RecursoInventario, recurso_id).cantidad_total == 14


def test_listado_sin_cloud_responde_igual(cloud):
    cliente, sesiones, simulado = cloud
    recurso_id = _vinculado(sesiones)
    simulado.caido = True
    respuesta = cliente.get(RUTA, headers=cabecera(ONG))
    assert respuesta.status_code == 200, respuesta.text
    fila = next(f for f in respuesta.json() if f["id"] == recurso_id)
    assert fila["tipo_recurso_id"] == 5
    assert fila["comprometido"] is None and fila["disponible"] is None and fila["sincronizado"] is False


def test_listado_acepta_formato_viejo_de_disponibilidad(cloud, monkeypatch):
    cliente, sesiones, _ = cloud
    recurso_id = _vinculado(sesiones)
    monkeypatch.setattr(cloud_client, "disponibilidad_ong", lambda ong_id, token: httpx.Response(
        200, json=[{"tipo_recurso_id": 5, "total": 10, "comprometido": 1, "disponible": 9}]))
    fila = next(f for f in cliente.get(RUTA, headers=cabecera(ONG)).json() if f["id"] == recurso_id)
    assert fila["disponible"] == 9 and fila["sincronizado"] is True
