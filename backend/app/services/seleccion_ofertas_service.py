"""Confirma la selección local mediante el contrato de la tarea de Bonita."""

import json
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dto.ofertas_dto import SeleccionOfertasRespuesta
from ..integrations.bonita.client import BonitaClientError, BonitaTaskConflictError, bonita_client
from ..models import AvisoAdjudicacion, EstadoEmergencia
from ..repositories import EmergenciaRepository, OfertaRepository


MENSAJE_EN_EVALUACION = (
    "La emergencia está en evaluación del Centro Coordinador: "
    "la cobertura no alcanzó y todavía no se puede adjudicar"
)


def conflicto(detalle: str) -> None:
    raise HTTPException(status_code=409, detail=detalle)


def pares_de(filas: list) -> set[tuple[int, int]]:
    if not isinstance(filas, list):
        conflicto("La selección del caso no tiene un formato válido")
    pares = set()
    for fila in filas:
        if not isinstance(fila, dict):
            conflicto("La selección del caso no tiene un formato válido")
        par = (fila.get("oferta_id"), fila.get("lote_id"))
        if any(type(valor) is not int or valor <= 0 for valor in par):
            conflicto("Los identificadores de oferta y lote deben ser positivos")
        if par in pares:
            conflicto("La selección del caso contiene pares duplicados")
        pares.add(par)
    return pares


class SeleccionOfertasService:
    @staticmethod
    def _caso_id(emergencia):
        if not emergencia.bonita_case_id:
            conflicto("La emergencia no tiene un caso de Bonita asociado")
        try:
            caso_id = int(emergencia.bonita_case_id)
            if caso_id <= 0:
                raise ValueError()
            return caso_id
        except (TypeError, ValueError):
            conflicto("El identificador del caso de Bonita no es válido")

    async def _evaluacion(self, caso_id, emergencia_id, db=None):
        from .evaluacion_cloud_service import EvaluacionCloudService

        evaluacion = (await run_in_threadpool(EvaluacionCloudService.obtener, db, emergencia_id, caso_id)
                      if db is not None else None)
        if evaluacion is None:
            evaluacion = await self._leer_json(caso_id, "evaluacionJson")
        if evaluacion is None:
            conflicto("La evaluación del caso aún no está disponible")
        if (not isinstance(evaluacion, dict)
                or type(evaluacion.get("emergencia_id")) is not int
                or evaluacion["emergencia_id"] != emergencia_id):
            conflicto("La evaluación del caso no corresponde a esta emergencia")
        resultados = evaluacion.get("resultados")
        pares_de(resultados)
        cantidades = {}
        for fila in resultados:
            cantidad = fila.get("cantidad_verificada")
            if type(cantidad) is not int or cantidad < 0:
                conflicto("La evaluación del caso contiene una cantidad verificada inválida")
            cantidades[(fila["oferta_id"], fila["lote_id"])] = cantidad
        return cantidades

    @staticmethod
    def _validar_pares(pares, cantidades):
        for oferta_id, lote_id in sorted(pares):
            if cantidades.get((oferta_id, lote_id), 0) <= 0:
                conflicto(f"La oferta {oferta_id}, lote {lote_id}, debe tener una cantidad verificada positiva en el caso")

    @staticmethod
    def validada(oferta, cantidades) -> bool:
        """Mismo criterio que la confirmación: cada fila con cantidad verificada positiva."""
        return bool(oferta.items) and all(
            cantidades.get((oferta.id, item.lote_necesidad_id), 0) > 0 for item in oferta.items
        )

    async def verificar_validada(self, db: Session, emergencia, oferta) -> None:
        """Rechaza adjudicar una oferta que el Sistema Nacional no validó."""
        try:
            cantidades = await self._evaluacion(self._caso_id(emergencia), emergencia.id, db)
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo consultar la evaluación en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una evaluación inválida")
        if not self.validada(oferta, cantidades):
            conflicto("La oferta no fue validada por el Sistema Nacional")

    async def _tarea_seleccion(self, caso_id):
        tarea = await bonita_client.obtener_tarea_pendiente(caso_id, "Seleccionar oferta")
        if tarea is not None and not isinstance(tarea, dict):
            conflicto("La tarea Seleccionar oferta no tiene un formato válido")
        if tarea is not None and not isinstance(tarea, dict):
            conflicto("La tarea Seleccionar oferta no tiene un formato válido")
        if tarea is not None and (
            str(tarea.get("caseId")) != str(caso_id) or tarea.get("name") != "Seleccionar oferta"
        ):
            conflicto("La tarea no corresponde al caso y a la selección de esta emergencia")
        if tarea is not None and tarea.get("state", "ready") != "ready":
            conflicto("La tarea Seleccionar oferta aún no está lista")
        return tarea

    @staticmethod
    async def _en_evaluacion(caso_id) -> bool:
        """El camino alternativo (cobertura insuficiente) espera Evaluar proyecto."""
        tarea = await bonita_client.obtener_tarea_pendiente(caso_id, "Evaluar proyecto")
        return (isinstance(tarea, dict) and str(tarea.get("caseId")) == str(caso_id)
                and tarea.get("name") == "Evaluar proyecto" and tarea.get("state", "ready") == "ready")

    async def _verificar_etapa(self, caso_id) -> None:
        """Adjudicar exige Seleccionar oferta lista y Evaluar proyecto no lista."""
        if await self._en_evaluacion(caso_id) or await self._tarea_seleccion(caso_id) is None:
            conflicto(MENSAJE_EN_EVALUACION)

    async def verificar_etapa_adjudicacion(self, emergencia) -> None:
        """Rechaza adjudicar mientras Bonita no habilitó la selección de ofertas."""
        try:
            await self._verificar_etapa(self._caso_id(emergencia))
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo consultar la fase de selección en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una respuesta inválida al consultar la fase de selección")

    async def preparar(self, db: Session, oferta_id: int, servicio=None):
        from .ofertas_service import OfertaService

        servicio = servicio or OfertaService()
        try:
            emergencia, oferta = await run_in_threadpool(servicio._bloquear_oferta, db, oferta_id)
            anterior = await run_in_threadpool(servicio._validar_adjudicacion, db, emergencia, oferta, True)
            if not oferta.items:
                conflicto("La oferta seleccionada no tiene ítems")
            caso_id = self._caso_id(emergencia)
            await self._verificar_etapa(caso_id)
            cantidades = await self._evaluacion(caso_id, emergencia.id, db)
            if not self.validada(oferta, cantidades):
                conflicto("La oferta no fue validada por el Sistema Nacional")
            if anterior is not None:
                return anterior
            return await run_in_threadpool(servicio._marcar_oferta, db, emergencia, oferta, None, True)
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="No se pudo guardar la selección local; vuelva a intentar")
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo consultar la evaluación o la fase de selección en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una respuesta inválida al preparar la selección")
        finally:
            await run_in_threadpool(db.rollback)

    async def listar(self, db: Session, emergencia_id: int, solo_validadas: bool = False):
        from .ofertas_service import OfertaService

        servicio = OfertaService()
        emergencia = await run_in_threadpool(servicio._emergencias.obtener_emergencia_entidad, db, emergencia_id)
        ofertas = await run_in_threadpool(servicio.listar_ofertas_de_emergencia, db, emergencia_id)
        cantidades, tarea = {}, None
        try:
            if not ofertas or emergencia.estado not in (
                EstadoEmergencia.ESPERANDO_ADJUDICACION, EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA,
            ):
                conflicto("La emergencia aún no tiene una evaluación vigente para seleccionar")
            caso_id = self._caso_id(emergencia)
            cantidades = await self._evaluacion(caso_id, emergencia_id, db)
            tarea = await self._tarea_seleccion(caso_id)
        except (HTTPException, BonitaClientError, httpx.RequestError, KeyError, TypeError, ValueError):
            # La ausencia de resultado y la indisponibilidad no equivalen a cero.
            tarea = None
        pendiente = await run_in_threadpool(EmergenciaRepository().obtener_confirmacion, db, emergencia_id)
        for oferta in ofertas:
            marcada = oferta.adjudicada_en is not None
            final = emergencia.estado in (EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA)
            oferta.estado_seleccion = ("adjudicada" if final else "seleccionada_para_confirmar") if marcada else "sin_seleccionar"
            for item in oferta.items:
                item.cantidad_verificada = cantidades.get((oferta.id, item.lote_necesidad_id))
            oferta.puede_seleccionar = bool(
                not marcada and pendiente is None and tarea is not None
                and emergencia.estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
                and oferta.items and all((item.cantidad_verificada or 0) > 0 for item in oferta.items)
            )
        if solo_validadas and not await self._visible_para_municipio(emergencia):
            return []
        if solo_validadas:
            # El municipio solo ve lo validado; sin evaluación nacional no hay ninguna.
            return [oferta for oferta in ofertas if self.validada(oferta, cantidades)]
        return ofertas

    async def _visible_para_municipio(self, emergencia) -> bool:
        """Oculta las ofertas mientras el caso espera la decisión del coordinador.

        En espera de adjudicación se exige la misma etapa que para adjudicar;
        en etapas posteriores sólo se ocultan si Evaluar proyecto sigue lista.
        """
        esperando = emergencia.estado == EstadoEmergencia.ESPERANDO_ADJUDICACION
        try:
            caso_id = self._caso_id(emergencia)
            if esperando:
                await self._verificar_etapa(caso_id)
                return True
            return not await self._en_evaluacion(caso_id)
        except HTTPException:
            return False
        except (BonitaClientError, httpx.RequestError, KeyError, TypeError, ValueError):
            # Sin Bonita no se habilita una adjudicación nueva.
            return not esperando

    async def _guardar_confirmacion(self, db, emergencia, respuesta, ya_confirmada=False,
                                    ofertas=()):
        # Una respuesta perdida o un commit fallido se reconcilian con la
        # selección del caso. Nunca se retrocede una emergencia ya resuelta.
        notificar = emergencia.estado not in (EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA)
        adjudicadas = [oferta for oferta in ofertas if oferta.adjudicada_en is not None]
        if emergencia.estado != EstadoEmergencia.RESUELTA:
            emergencia.estado = EstadoEmergencia.EN_PROCESO
        if notificar:
            # La adjudicación y su aviso se confirman o revierten juntos.
            # El lock de emergencia serializa confirmadores y la PK deduplica.
            fecha_confirmacion = datetime.now(timezone.utc)
            for oferta in adjudicadas:
                if await run_in_threadpool(db.get, AvisoAdjudicacion, oferta.id) is None:
                    await run_in_threadpool(db.add, AvisoAdjudicacion(
                        oferta_id=oferta.id, creada_en=fecha_confirmacion,
                    ))
        await run_in_threadpool(EmergenciaRepository().eliminar_confirmacion, db, emergencia.id)
        await run_in_threadpool(db.commit)
        return respuesta.model_copy(update={"ya_confirmada": ya_confirmada})

    async def _leer_json(self, caso_id: int, nombre: str):
        valor = await bonita_client.obtener_variable_caso(caso_id, nombre)
        if valor is None or valor == "":
            return None
        try:
            return json.loads(valor)
        except (TypeError, ValueError):
            conflicto(f"La variable {nombre} del caso no contiene JSON válido")

    async def _ya_confirmada(self, caso_id: int, pares: set) -> bool:
        seleccion = await self._leer_json(caso_id, "seleccionOfertasJson")
        if seleccion is None:
            return False
        anteriores = pares_de(seleccion)
        if not anteriores:
            return False
        if anteriores != pares:
            conflicto("El caso ya confirmó una selección diferente; no se puede volver a ejecutar")
        return True

    async def confirmar(self, db: Session, emergencia_id: int) -> SeleccionOfertasRespuesta:
        # Mismo orden que la adjudicación y edición: emergencia → ofertas.
        # Se conserva el bloqueo hasta aceptar Bonita y guardar la etapa local.
        emergencia = await run_in_threadpool(
            EmergenciaRepository().obtener_por_id, db, emergencia_id, bloquear=True
        )
        try:
            if emergencia is None:
                raise HTTPException(status_code=404, detail="Emergencia no encontrada")
            if emergencia.estado not in (
                EstadoEmergencia.ESPERANDO_ADJUDICACION, EstadoEmergencia.EN_PROCESO,
                EstadoEmergencia.ESPERA_OFERTAS, EstadoEmergencia.RESUELTA,
            ):
                conflicto("La emergencia no está en una etapa que permita confirmar la selección")
            caso_id = self._caso_id(emergencia)
            ofertas = await run_in_threadpool(
                OfertaRepository().listar_de_emergencia, db, emergencia_id, bloquear=True
            )
            filas = []
            for oferta in ofertas:
                if oferta.adjudicada_en is not None:
                    if not oferta.items:
                        conflicto("La oferta adjudicada no tiene ítems")
                    for item in oferta.items:
                        if item.cantidad_ofrecida <= 0 or item.lote_necesidad.emergencia_id != emergencia_id:
                            conflicto("La oferta adjudicada contiene un ítem inválido")
                        filas.append({"oferta_id": oferta.id, "lote_id": item.lote_necesidad_id})
            pares = pares_de(filas)
            if not pares:
                conflicto("Debe adjudicar al menos una oferta antes de confirmar la selección")
            pendiente = await run_in_threadpool(
                EmergenciaRepository().obtener_confirmacion, db, emergencia_id
            )
            if pendiente is not None and (
                pendiente.caso_id != str(caso_id)
                or pares_de(json.loads(pendiente.seleccion_json)) != pares
            ):
                conflicto("La selección local no coincide con la confirmación pendiente del caso")
            respuesta = SeleccionOfertasRespuesta(emergencia_id=emergencia_id, cantidad_pares=len(pares))
            if await self._ya_confirmada(caso_id, pares):
                return await self._guardar_confirmacion(db, emergencia, respuesta, True, ofertas)
            if emergencia.estado == EstadoEmergencia.RESUELTA:
                conflicto("La emergencia resuelta no puede confirmar una nueva selección")
            cantidades = await self._evaluacion(caso_id, emergencia_id, db)
            self._validar_pares(pares, cantidades)
            tarea = await self._tarea_seleccion(caso_id)
            if tarea is None:
                if await self._ya_confirmada(caso_id, pares):
                    return await self._guardar_confirmacion(db, emergencia, respuesta, True, ofertas)
                conflicto("El caso no tiene pendiente la tarea Seleccionar oferta; la selección aún no está confirmada")
            miembro = await bonita_client.obtener_miembro_actor(int(tarea["actorId"]), solo_usuarios=True)
            if not miembro or int(miembro.get("user_id", 0)) <= 0:
                conflicto("El actor de Seleccionar oferta no tiene un usuario directo autorizado")
            usuario_id = int(miembro["user_id"])
            asignado = int(tarea.get("assigned_id") or 0)
            if asignado > 0 and asignado != usuario_id:
                conflicto("La tarea Seleccionar oferta ya está asignada a otro usuario")
            if pendiente is None:
                # Persistir antes de cualquier intento de ejecución: un timeout
                # puede ocultar aceptación y un rollback local no debe liberar
                # nuevas marcas. Este commit libera los locks; reentrar obliga
                # a retomarlos y reconciliar lo que hizo otro confirmador.
                await run_in_threadpool(
                    EmergenciaRepository().preparar_confirmacion,
                    db, emergencia_id, caso_id, json.dumps(filas),
                )
                await run_in_threadpool(db.commit)
                return await self.confirmar(db, emergencia_id)
            try:
                if asignado <= 0:
                    await bonita_client.asignar_tarea(tarea["id"], usuario_id)
                await bonita_client.ejecutar_tarea(tarea["id"], {"seleccionInput": filas})
            except (BonitaClientError, httpx.RequestError) as exc:
                # Una respuesta perdida puede ocultar una ejecución exitosa.
                if await self._ya_confirmada(caso_id, pares):
                    return await self._guardar_confirmacion(db, emergencia, respuesta, True, ofertas)
                if isinstance(exc, BonitaTaskConflictError):
                    conflicto("Bonita no pudo confirmar la tarea; actualice la emergencia y vuelva a intentar")
                raise
            return await self._guardar_confirmacion(db, emergencia, respuesta, False, ofertas)
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="No se pudo guardar la confirmación local; vuelva a intentar")
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo consultar o confirmar la selección en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una respuesta inválida al confirmar la selección")
        finally:
            await run_in_threadpool(db.rollback)
