"""Reserva nacional única, con intención local persistida antes del envío."""

import json
from collections import defaultdict

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..integrations import cloud_client
from ..integrations.bonita.client import BonitaClientError
from ..models import EstadoEmergencia, LoteRecursoCloud, OfertaAyuda, RegistroRecursos
from ..schemas.evaluacion_cloud_schema import RespuestaCloud
from .emergencias_service import EmergenciaService
from .evaluacion_cloud_service import EvaluacionCloudService
from .seleccion_ofertas_service import SeleccionOfertasService


def conflicto(detalle):
    raise HTTPException(409, detalle)


def canonico(valor):
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), allow_nan=False)


class RegistroRecursosService:
    async def registrar(self, db: Session, emergencia_id: int, datos) -> None:
        try:
            requiere_prueba = await run_in_threadpool(self._requiere_prueba, db, emergencia_id, datos)
            if requiere_prueba:
                pares = {(par.oferta_id, par.lote_id) for par in datos.seleccion}
                if not await SeleccionOfertasService()._ya_confirmada(datos.caso_id, pares):
                    conflicto("La selección del caso aún no está confirmada en Bonita")
            await run_in_threadpool(self._registrar, db, emergencia_id, datos)
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo comprobar la selección confirmada en Bonita") from None
        except (ValueError, TypeError, KeyError):
            raise HTTPException(503, "No se pudo validar la selección confirmada del caso") from None
        except SQLAlchemyError:
            raise HTTPException(503, "No se pudo consultar el registro de recursos") from None
        finally:
            await run_in_threadpool(db.rollback)

    @staticmethod
    def _requiere_prueba(db, emergencia_id, datos):
        try:
            emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id)
            if emergencia.bonita_case_id != str(datos.caso_id):
                conflicto("El caso no corresponde a la emergencia")
            return db.get(RegistroRecursos, emergencia_id, populate_existing=True) is None
        finally:
            # La consulta remota de selección jamás conserva una transacción.
            db.rollback()

    def _registrar(self, db: Session, emergencia_id: int, datos) -> None:
        try:
            solicitud = self._preparar(db, emergencia_id, datos)
            if solicitud is None:
                return
            # _preparar ya confirmó ENVIADO y liberó el lock. Ninguna
            # transacción municipal permanece abierta durante el HTTP.
            try:
                token = cloud_client.obtener_token_aplicacion()
            except cloud_client.AutenticacionAplicacionError:
                self._guardar(db, emergencia_id, "RECHAZADO")
                raise HTTPException(503, "No se pudo autenticar la aplicación en Cloud; puede reintentar") from None
            try:
                respuesta = cloud_client.bloquear_recursos(solicitud, token)
            except (httpx.RequestError, httpx.InvalidURL):
                raise HTTPException(503, "El resultado de la reserva es incierto; requiere conciliación antes de reintentar") from None
            if respuesta.status_code in (401, 403, 404, 409, 422):
                # Estos rechazos del contrato Cloud no escriben compromisos.
                self._guardar(db, emergencia_id, "RECHAZADO")
                conflicto("Cloud rechazó la reserva sin registrar recursos; puede reintentar la misma selección")
            if respuesta.status_code != 200:
                raise HTTPException(503, "El resultado de la reserva es incierto; requiere conciliación antes de reintentar")
            try:
                recibo = respuesta.json()
                self._validar_recibo(solicitud, recibo)
                canonico(recibo)
            except (ValueError, TypeError, KeyError):
                raise HTTPException(503, "Cloud no confirmó exactamente la reserva solicitada; requiere conciliación") from None
            self._guardar(db, emergencia_id, "CONFIRMADO", recibo)
        except SQLAlchemyError:
            # Si falla guardar el recibo, ENVIADO sigue durable: no reenviar.
            raise HTTPException(503, "No se pudo guardar el registro de recursos; requiere verificar el intento antes de reintentar") from None
        finally:
            db.rollback()

    def _preparar(self, db, emergencia_id, datos):
        emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id, bloquear=True)
        if emergencia.bonita_case_id != str(datos.caso_id):
            conflicto("El caso no corresponde a la emergencia")
        seleccion = canonico(sorted((par.model_dump() for par in datos.seleccion),
                                   key=lambda par: (par["oferta_id"], par["lote_id"])))
        registro = db.get(RegistroRecursos, emergencia_id, populate_existing=True)
        if registro is not None:
            if registro.caso_id != str(datos.caso_id) or registro.seleccion_json != seleccion:
                conflicto("La emergencia ya tiene un intento con otro caso o selección")
            if registro.estado == "CONFIRMADO":
                return None
            if registro.estado != "RECHAZADO":
                conflicto("La reserva tiene un envío pendiente o incierto; requiere conciliación y no se reenviará")
        if emergencia.estado != EstadoEmergencia.EN_PROCESO:
            conflicto("La selección debe estar confirmada y la emergencia en proceso para registrar recursos")
        ofertas = db.query(OfertaAyuda).filter_by(emergencia_id=emergencia_id).all()
        pares = {(par.oferta_id, par.lote_id) for par in datos.seleccion}
        adjudicados = set()
        for oferta in ofertas:
            if oferta.adjudicada_en is not None:
                if not oferta.items:
                    conflicto("La oferta adjudicada no tiene ítems")
                for item in oferta.items:
                    if item.cantidad_ofrecida <= 0 or item.lote_necesidad.emergencia_id != emergencia_id:
                        conflicto("La oferta adjudicada contiene un ítem inválido")
                    adjudicados.add((oferta.id, item.lote_necesidad_id))
        if pares != adjudicados:
            conflicto("La selección del caso no coincide con todas las ofertas adjudicadas")
        if registro is None:
            solicitud = self._construir(db, emergencia_id, datos.caso_id, pares)
            registro = RegistroRecursos(emergencia_id=emergencia_id, caso_id=str(datos.caso_id),
                                       seleccion_json=seleccion, solicitud_json=canonico(solicitud), estado="ENVIADO")
            db.add(registro)
        else:
            solicitud = json.loads(registro.solicitud_json)
            registro.estado = "ENVIADO"
        db.commit()
        return solicitud

    @staticmethod
    def _construir(db, emergencia_id, caso_id, pares):
        try:
            evaluacion = EvaluacionCloudService.obtener(db, emergencia_id, caso_id)
            if evaluacion is None:
                conflicto("Se requiere la evaluación local de la ronda actual para registrar recursos")
            ronda = EvaluacionCloudService.ultima(db, emergencia_id)
            respuesta = RespuestaCloud.model_validate(evaluacion)
            solicitud = json.loads(ronda.solicitud_json)
            if respuesta.emergencia_id != emergencia_id or solicitud["emergencia_id"] != emergencia_id:
                raise ValueError()
            filas = {(fila["oferta_id"], fila["lote_id"]): fila for fila in solicitud["ofertas"]}
            resultados = {(fila.oferta_id, fila.lote_id): fila for fila in respuesta.resultados}
            if len(resultados) != len(respuesta.resultados) or len(filas) != len(solicitud["ofertas"]):
                raise ValueError()
            tipos = {fila.lote_id: fila.tipo_recurso_id for fila in db.query(LoteRecursoCloud)
                     .filter(LoteRecursoCloud.lote_id.in_({lote for _, lote in pares}))}
            lotes = {lote["lote_id"]: lote["tipo_recurso_id"] for lote in solicitud["lotes"]}
            cantidades = defaultdict(int)
            for par in sorted(pares):
                resultado, fila = resultados[par], filas[par]
                tipo = tipos[par[1]]
                if lotes[par[1]] != tipo or resultado.cantidad_verificada <= 0 or resultado.nivel_habilitacion == "SIN_DISPONIBILIDAD":
                    raise ValueError()
                declarados = defaultdict(int)
                for aporte in fila["aportes"]:
                    for item in aporte["items"]:
                        if item["tipo_recurso_id"] != tipo or type(item["cantidad"]) is not int or item["cantidad"] <= 0:
                            raise ValueError()
                        declarados[(aporte["ong_id"], tipo)] += item["cantidad"]
                verificados = defaultdict(int)
                participantes = set()
                for participante in resultado.participantes:
                    if participante.ong_id in participantes:
                        raise ValueError()
                    participantes.add(participante.ong_id)
                    for capacidad in participante.capacidades_habilitadas:
                        if capacidad.cantidad_verificada > capacidad.cantidad_ofrecida:
                            raise ValueError()
                        if not participante.habilitada or capacidad.cantidad_verificada == 0:
                            continue
                        clave = (participante.ong_id, capacidad.tipo_recurso_id)
                        if capacidad.tipo_recurso_id != tipo or clave not in declarados:
                            raise ValueError()
                        verificados[clave] += capacidad.cantidad_verificada
                        if verificados[clave] > declarados[clave]:
                            raise ValueError()
                if sum(verificados.values()) != resultado.cantidad_verificada:
                    raise ValueError()
                for clave, cantidad in verificados.items():
                    cantidades[clave] += cantidad
            agrupados = defaultdict(list)
            for (ong_id, item_id), cantidad in sorted(cantidades.items()):
                agrupados[ong_id].append({"item_id": item_id, "cantidad": cantidad})
            if not agrupados:
                raise ValueError()
            return {"emergencia_id": emergencia_id, "ongs": [
                {"ong_id": ong_id, "items": items} for ong_id, items in sorted(agrupados.items())]}
        except (ValidationError, ValueError, TypeError, KeyError):
            conflicto("La evaluación local no contiene aportes verificados válidos de la selección y ronda actuales")

    @staticmethod
    def _validar_recibo(solicitud, recibo):
        if (not isinstance(recibo, dict) or type(recibo.get("emergencia_id")) is not int
                or recibo["emergencia_id"] != solicitud["emergencia_id"] or recibo.get("lote_id") is not None):
            raise ValueError()
        esperados = {(ong["ong_id"], item["item_id"]): item["cantidad"]
                     for ong in solicitud["ongs"] for item in ong["items"]}
        recibidos = {}
        for fila in recibo["bloqueados"]:
            if (any(type(fila[campo]) is not int or fila[campo] <= 0 for campo in ("ong_id", "item_id", "cantidad"))
                    or fila["estado"] != "BLOQUEADO"):
                raise ValueError()
            clave = (fila["ong_id"], fila["item_id"])
            if clave in recibidos:
                raise ValueError()
            recibidos[clave] = fila["cantidad"]
        if (recibidos != esperados or type(recibo.get("total_bloqueado")) is not int
                or recibo["total_bloqueado"] != sum(esperados.values())):
            raise ValueError()

    @staticmethod
    def _guardar(db, emergencia_id, estado, recibo=None):
        EmergenciaService().obtener_emergencia_entidad(db, emergencia_id, bloquear=True)
        registro = db.get(RegistroRecursos, emergencia_id, populate_existing=True)
        registro.estado = estado
        if recibo is not None:
            registro.respuesta_json = canonico(recibo)
        db.commit()
