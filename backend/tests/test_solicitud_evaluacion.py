"""Contrato HTTP de la solicitud para Cloud, con autenticación y base aislada."""

import httpx
import pytest

from app.integrations import cloud_client
from app.models import Emergencia, EstadoEmergencia, Usuario
from app.services.permisos_service import AUDITOR, COORDINADOR, ONG, OPERADOR
from test_permisos_api import cabecera, entorno, estado


def test_lote_expone_referencia_nacional_en_alta_lectura_y_edicion(entorno):
    cliente, sesiones, _ = entorno
    cabeceras = cabecera(COORDINADOR)
    datos = {"tipo": "Agua", "cantidad": 10, "unidad": "litros",
             "descripcion": "Agua potable", "tipo_recurso_id": 41}
    alta = cliente.post("/api/v1/emergencias/1/lotes", headers=cabeceras, json=datos)
    assert alta.status_code == 201, alta.text
    esperado = {**datos, "id": alta.json()["id"], "emergencia_id": 1}
    assert alta.json() == esperado
    lote_id = esperado["id"]

    def verificar_lecturas():
        detalle = cliente.get(f"/api/v1/lotes/{lote_id}", headers=cabeceras)
        assert detalle.status_code == 200, detalle.text
        assert detalle.json() == esperado
        lotes = cliente.get("/api/v1/emergencias/1/lotes", headers=cabeceras)
        assert lotes.status_code == 200, lotes.text
        assert next(lote for lote in lotes.json() if lote["id"] == lote_id) == esperado
        assert next(lote for lote in lotes.json() if lote["id"] == 1)["tipo_recurso_id"] is None
        for ruta in ("/api/v1/emergencias/1", "/api/v1/emergencias",
                     "/api/v1/emergencias/bandeja?publicada=false"):
            respuesta = cliente.get(ruta, headers=cabeceras)
            assert respuesta.status_code == 200, respuesta.text
            cuerpo = respuesta.json()
            emergencia = (cuerpo if ruta.endswith("/1") else
                          next(fila for fila in (cuerpo["items"] if "items" in cuerpo else cuerpo)
                               if fila["id"] == 1))
            assert next(lote for lote in emergencia["lotes"] if lote["id"] == lote_id) == esperado

    verificar_lecturas()
    for cambios in ({"tipo_recurso_id": 73}, {"cantidad": 12}):
        actualizado = cliente.patch(f"/api/v1/lotes/{lote_id}", headers=cabeceras, json=cambios)
        assert actualizado.status_code == 200, actualizado.text
        esperado.update(cambios)
        assert actualizado.json() == esperado
        verificar_lecturas()
    with sesiones() as db:
        from app.models import LoteNecesidad

        assert db.get(LoteNecesidad, lote_id).referencia_cloud.tipo_recurso_id == 73


@pytest.mark.parametrize("cambios", [{"tipo": "Abrigo"}, {"unidad": "bidones"},
                                     {"tipo_recurso_id": None}])
def test_lectura_lote_conserva_referencia_opcional_e_invalidacion(entorno, cambios):
    cliente, _, _ = entorno
    cabeceras = cabecera(COORDINADOR)
    historico = cliente.get("/api/v1/lotes/1", headers=cabeceras)
    assert historico.status_code == 200, historico.text
    assert historico.json() == {"id": 1, "emergencia_id": 1, "tipo": "agua", "cantidad": 10,
                                "unidad": None, "descripcion": None, "tipo_recurso_id": None}
    alta = cliente.post("/api/v1/emergencias/1/lotes", headers=cabeceras,
                        json={"tipo": "Agua", "cantidad": 5})
    assert alta.status_code == 201 and alta.json()["tipo_recurso_id"] is None
    vinculacion = cliente.patch("/api/v1/lotes/1", headers=cabeceras,
                               json={"tipo_recurso_id": 41})
    assert vinculacion.status_code == 200 and vinculacion.json()["tipo_recurso_id"] == 41
    actualizado = cliente.patch("/api/v1/lotes/1", headers=cabeceras, json=cambios)
    assert actualizado.status_code == 200 and actualizado.json()["tipo_recurso_id"] is None
    lectura = cliente.get("/api/v1/lotes/1", headers=cabeceras)
    assert lectura.status_code == 200 and lectura.json() == actualizado.json()


@pytest.mark.parametrize("ruta", ["/api/v1/emergencias/1/lotes", "/api/v1/emergencias/1",
                                  "/api/v1/emergencias", "/api/v1/emergencias/bandeja?publicada=false"])
def test_listar_lotes_carga_referencias_sin_consultas_por_lote(entorno, ruta):
    from sqlalchemy import event

    cliente, sesiones, _ = entorno
    cabeceras = cabecera(COORDINADOR)
    consultas = []
    motor = sesiones.kw["bind"]

    def registrar(conexion, cursor, sentencia, parametros, contexto, multiples):
        consultas.append(sentencia.lower())

    def contar_lectura():
        consultas.clear()
        event.listen(motor, "before_cursor_execute", registrar)
        try:
            respuesta = cliente.get(ruta, headers=cabeceras)
        finally:
            event.remove(motor, "before_cursor_execute", registrar)
        assert respuesta.status_code == 200, respuesta.text
        return len(consultas)

    con_un_lote = contar_lectura()
    for nacional in (41, 73, 89):
        alta = cliente.post("/api/v1/emergencias/1/lotes", headers=cabeceras,
                            json={"tipo": "Agua", "cantidad": 5, "tipo_recurso_id": nacional})
        assert alta.status_code == 201, alta.text
    assert contar_lectura() == con_un_lote


@pytest.fixture
def solicitud(entorno, monkeypatch):
    cliente, sesiones, _ = entorno
    nacionales = iter((901, 907))

    def registrar(cuit, nombre, email, token):
        return httpx.Response(201, json={"id": next(nacionales), "cuit": cuit,
                                       "razon_social": nombre, "email": email})

    monkeypatch.setattr(cloud_client, "registrar_ong", registrar)
    assert cliente.patch("/api/v1/lotes/1", headers=cabecera(COORDINADOR),
                         json={"tipo_recurso_id": 41}).status_code == 200
    organizaciones = []
    for numero in (1, 2):
        respuesta = cliente.post("/api/v1/organizaciones", headers=cabecera(COORDINADOR),
                                 json={"nombre": f"ONG {numero}", "cuit": f"30-0000000{numero}-1",
                                       "email": f"contacto{numero}@example.org"})
        assert respuesta.status_code == 201, respuesta.text
        organizaciones.append(respuesta.json()["id"])
    lotes = []
    for tipo, nacional in (("Agua", 41), ("Abrigo", 73)):
        respuesta = cliente.post("/api/v1/emergencias/1/lotes", headers=cabecera(COORDINADOR),
                                 json={"tipo": tipo, "cantidad": 10, "tipo_recurso_id": nacional})
        assert respuesta.status_code == 201, respuesta.text
        lotes.append(respuesta.json()["id"])
    with sesiones() as db:
        emergencia = db.get(Emergencia, 1)
        emergencia.publicada = True
        emergencia.estado = EstadoEmergencia.ESPERA_OFERTAS
        db.get(Usuario, 3).organizacion_id = organizaciones[0]
        db.commit()
    return cliente, sesiones, organizaciones, lotes


def crear_oferta(solicitud, conjunta=True):
    cliente, _, organizaciones, lotes = solicitud
    items = [{"lote_necesidad_id": lote, "cantidad_ofrecida": 8,
              **({"aportes": [{"organizacion_id": organizaciones[0], "cantidad": cantidad},
                               {"organizacion_id": organizaciones[1], "cantidad": 8 - cantidad}]}
                 if conjunta else {})} for lote, cantidad in zip(lotes, (3, 6))]
    return cliente.post("/api/v1/ofertas", headers=cabecera(ONG),
                        json={"emergencia_id": 1, "organizacion_id": organizaciones[0],
                              "organizaciones_ids": organizaciones if conjunta else [], "items": items})


def test_solicitud_conserva_oferta_lote_y_aportes_efectivos(solicitud):
    cliente, sesiones, _, lotes = solicitud
    alta = crear_oferta(solicitud)
    assert alta.status_code == 201, alta.text
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo == {"emergencia_id": 1,
                      "lotes": [{"lote_id": 1, "tipo_recurso_id": 41, "cantidad_requerida": 10},
                                *[{"lote_id": lote, "tipo_recurso_id": tipo, "cantidad_requerida": 10}
                                  for lote, tipo in zip(lotes, (41, 73))]],
                      "ofertas": [{"oferta_id": alta.json()["id"], "lote_id": lote,
                                   "ong_responsable_id": 901,
                                   "aportes": [{"ong_id": 901, "items": [{"tipo_recurso_id": tipo, "cantidad": cantidad}]},
                                               {"ong_id": 907, "items": [{"tipo_recurso_id": tipo, "cantidad": 8 - cantidad}]}]}
                                  for lote, tipo, cantidad in zip(lotes, (41, 73), (3, 6))]}
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("rol,esperado", [(COORDINADOR, 409), (AUDITOR, 409), (ONG, 403),
                                          (OPERADOR, 403), (None, 401)])
def test_ruta_autentica_y_no_enumera_ongs(entorno, rol, esperado):
    cliente, sesiones, _ = entorno
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/2/solicitud-evaluacion",
                            headers=cabecera(rol) if rol else {})
    assert respuesta.status_code == esperado, respuesta.text
    assert estado(sesiones) == anterior


def test_emergencia_inexistente_y_lotes_historicos(entorno):
    cliente, sesiones, _ = entorno
    anterior = estado(sesiones)
    assert cliente.get("/api/v1/emergencias/999/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 404
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409 and "lote 1" in respuesta.json()["detail"].lower()
    assert estado(sesiones) == anterior


def test_oferta_individual_y_emergencia_sin_ofertas(solicitud):
    cliente, sesiones, _, _ = solicitud
    vacia = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(AUDITOR))
    assert vacia.status_code == 200 and vacia.json()["ofertas"] == []
    alta = crear_oferta(solicitud, conjunta=False)
    assert alta.status_code == 201, alta.text
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(AUDITOR))
    assert respuesta.status_code == 200, respuesta.text
    assert [fila["aportes"] for fila in respuesta.json()["ofertas"]] == [
        [{"ong_id": 901, "items": [{"tipo_recurso_id": tipo, "cantidad": 8}]}]
        for tipo in (41, 73)]
    # Se conserva el contrato previo de los ítems en los listados.
    assert set(alta.json()["items"][0]) == {"id", "lote_necesidad_id", "cantidad_ofrecida",
                                           "descripcion", "finalizado_en"}


def test_consorcio_sin_reparto_no_inventa_cantidades(solicitud):
    cliente, sesiones, organizaciones, lotes = solicitud
    respuesta = cliente.post("/api/v1/ofertas", headers=cabecera(ONG),
                            json={"emergencia_id": 1, "organizacion_id": organizaciones[0],
                                  "organizaciones_ids": organizaciones,
                                  "items": [{"lote_necesidad_id": lotes[0], "cantidad_ofrecida": 8}]})
    assert respuesta.status_code == 201, respuesta.text
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409 and "aportes" in respuesta.json()["detail"].lower()
    assert estado(sesiones) == anterior


@pytest.mark.parametrize("aportes,esperado", [
    ([{"organizacion_id": 3, "cantidad": 0}], 422),
    ([{"organizacion_id": 3, "cantidad": 8}, {"organizacion_id": 3, "cantidad": 1}], 400),
    ([{"organizacion_id": 999, "cantidad": 8}], 400),
    ([{"organizacion_id": 3, "cantidad": 7}], 400),
])
def test_rechazo_aportes_es_atomico(solicitud, aportes, esperado):
    cliente, sesiones, organizaciones, lotes = solicitud
    anterior = estado(sesiones)
    respuesta = cliente.post("/api/v1/ofertas", headers=cabecera(ONG),
                            json={"emergencia_id": 1, "organizacion_id": organizaciones[0],
                                  "organizaciones_ids": organizaciones,
                                  "items": [{"lote_necesidad_id": lotes[0], "cantidad_ofrecida": 8,
                                             "aportes": aportes}]})
    assert respuesta.status_code == esperado, respuesta.text
    assert estado(sesiones) == anterior


def test_cambio_participantes_no_reutiliza_aportes_obsoletos(solicitud):
    cliente, _, organizaciones, _ = solicitud
    alta = crear_oferta(solicitud)
    assert alta.status_code == 201, alta.text
    oferta_id = alta.json()["id"]
    # Pasar a individual usa únicamente el total de su responsable.
    respuesta = cliente.patch(f"/api/v1/ofertas/{oferta_id}", headers=cabecera(ONG),
                              json={"organizaciones_ids": []})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR)).json()
    assert cuerpo["ofertas"][0]["aportes"] == [{"ong_id": 901, "items": [{"tipo_recurso_id": 41, "cantidad": 8}]}]
    # Volver a conjunta exige declarar de nuevo el reparto.
    assert cliente.patch(f"/api/v1/ofertas/{oferta_id}", headers=cabecera(ONG),
                         json={"organizaciones_ids": organizaciones}).status_code == 200
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409


def test_edicion_lote_invalida_tipo_nacional_anterior(entorno):
    cliente, sesiones, _ = entorno
    assert cliente.patch("/api/v1/lotes/1", headers=cabecera(COORDINADOR),
                         json={"tipo_recurso_id": 41}).status_code == 200
    assert cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR)).status_code == 200
    assert cliente.patch("/api/v1/lotes/1", headers=cabecera(COORDINADOR),
                         json={"cantidad": 12}).status_code == 200
    assert cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR)).json()["lotes"][0]["cantidad_requerida"] == 12
    assert cliente.patch("/api/v1/lotes/1", headers=cabecera(COORDINADOR),
                         json={"tipo": "Abrigo"}).status_code == 200
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409
    assert estado(sesiones) == anterior


def test_sin_lotes_y_ong_historica_no_comparan_ids_locales(entorno):
    cliente, sesiones, _ = entorno
    assert cliente.delete("/api/v1/lotes/1", headers=cabecera(COORDINADOR)).status_code == 204
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409 and "al menos uno" in respuesta.json()["detail"]
    with sesiones() as db:
        db.get(Emergencia, 2).publicada = False
        db.commit()
    assert cliente.patch("/api/v1/lotes/2", headers=cabecera(COORDINADOR),
                         json={"tipo_recurso_id": 41}).status_code == 200
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/2/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409 and "organización 1" in respuesta.json()["detail"]
    assert estado(sesiones) == anterior


def test_editar_items_reemplaza_aportes_y_rechazo_conserva_oferta(solicitud):
    cliente, sesiones, organizaciones, lotes = solicitud
    alta = crear_oferta(solicitud)
    oferta_id = alta.json()["id"]
    anterior = estado(sesiones)
    respuesta = cliente.patch(f"/api/v1/ofertas/{oferta_id}", headers=cabecera(ONG),
                              json={"observaciones": "No debe persistir",
                                    "items": [{"lote_necesidad_id": lotes[0], "cantidad_ofrecida": 8,
                                               "aportes": [{"organizacion_id": organizaciones[0], "cantidad": 7}]}]})
    assert respuesta.status_code == 400 and estado(sesiones) == anterior
    respuesta = cliente.patch(f"/api/v1/ofertas/{oferta_id}", headers=cabecera(ONG),
                              json={"items": [{"lote_necesidad_id": lotes[1], "cantidad_ofrecida": 9,
                                               "aportes": [{"organizacion_id": organizaciones[1], "cantidad": 9}]}]})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR)).json()
    assert len(cuerpo["ofertas"]) == 1
    assert cuerpo["ofertas"][0]["aportes"] == [{"ong_id": 907, "items": [{"tipo_recurso_id": 73, "cantidad": 9}]}]


def test_create_all_agrega_referencias_sin_modificar_registros():
    from sqlalchemy import create_engine, inspect
    from app.database import Base
    from app.models import Organizacion

    motor = create_engine("sqlite://")
    nuevas = {"organizaciones_cloud", "lotes_recursos_cloud", "aportes_oferta_items"}
    anteriores = [tabla for tabla in Base.metadata.sorted_tables if tabla.name not in nuevas]
    Base.metadata.create_all(motor, tables=anteriores)
    columnas = {tabla.name: [columna["name"] for columna in inspect(motor).get_columns(tabla.name)]
                for tabla in anteriores}
    with motor.begin() as conexion:
        conexion.execute(Organizacion.__table__.insert().values(id=1, nombre="Registro previo"))
    Base.metadata.create_all(motor)
    assert nuevas.issubset(inspect(motor).get_table_names())
    for nombre, esperadas in columnas.items():
        assert [columna["name"] for columna in inspect(motor).get_columns(nombre)] == esperadas
    with motor.connect() as conexion:
        assert conexion.execute(Organizacion.__table__.select()).one().nombre == "Registro previo"
    motor.dispose()


def test_vinculacion_nacional_ambigua_no_combina_ongs(solicitud):
    from app.models import OrganizacionCloud

    cliente, sesiones, organizaciones, _ = solicitud
    assert crear_oferta(solicitud).status_code == 201
    with sesiones() as db:
        db.get(OrganizacionCloud, organizaciones[1]).ong_id = 901
        db.commit()
    anterior = estado(sesiones)
    respuesta = cliente.get("/api/v1/emergencias/1/solicitud-evaluacion", headers=cabecera(COORDINADOR))
    assert respuesta.status_code == 409 and "mismo ong_id" in respuesta.json()["detail"]
    assert estado(sesiones) == anterior
