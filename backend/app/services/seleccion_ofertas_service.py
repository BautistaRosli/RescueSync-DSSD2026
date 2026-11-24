"""Confirma la selección local mediante el contrato de la tarea de Bonita."""

import json

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dto.ofertas_dto import SeleccionOfertasRespuesta
from ..integrations.bonita.client import BonitaClientError, BonitaTaskConflictError, bonita_client
from ..repositories import EmergenciaRepository, OfertaRepository


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
        # El bloqueo de fila serializa confirmaciones en PostgreSQL. Se libera
        # incluso ante errores; no se escriben estados locales ni se envían correos.
        emergencia = await run_in_threadpool(
            EmergenciaRepository().obtener_por_id, db, emergencia_id, bloquear=True
        )
        try:
            if emergencia is None:
                raise HTTPException(status_code=404, detail="Emergencia no encontrada")
            if not emergencia.bonita_case_id:
                conflicto("La emergencia no tiene un caso de Bonita asociado")
            try:
                caso_id = int(emergencia.bonita_case_id)
                if caso_id <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                conflicto("El identificador del caso de Bonita no es válido")
            ofertas = await run_in_threadpool(OfertaRepository().listar_de_emergencia, db, emergencia_id)
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
            respuesta = SeleccionOfertasRespuesta(emergencia_id=emergencia_id, cantidad_pares=len(pares))
            if await self._ya_confirmada(caso_id, pares):
                return respuesta.model_copy(update={"ya_confirmada": True})
            evaluacion = await self._leer_json(caso_id, "evaluacionJson")
            if not isinstance(evaluacion, dict) or evaluacion.get("emergencia_id") != emergencia_id:
                conflicto("La evaluación del caso no corresponde a esta emergencia")
            resultados = evaluacion.get("resultados")
            pares_de(resultados)
            validos = {(fila["oferta_id"], fila["lote_id"]) for fila in resultados
                       if type(fila.get("cantidad_verificada")) is int and fila["cantidad_verificada"] > 0}
            if not pares.issubset(validos):
                conflicto("Cada oferta y lote adjudicado debe tener una cantidad verificada positiva en el caso")
            tarea = await bonita_client.obtener_tarea_pendiente(caso_id, "Seleccionar oferta")
            if tarea is None:
                if await self._ya_confirmada(caso_id, pares):
                    return respuesta.model_copy(update={"ya_confirmada": True})
                conflicto("El caso no tiene pendiente la tarea Seleccionar oferta; la selección aún no está confirmada")
            if str(tarea.get("caseId")) != str(caso_id) or tarea.get("name") != "Seleccionar oferta":
                conflicto("La tarea no corresponde al caso y a la selección de esta emergencia")
            miembro = await bonita_client.obtener_miembro_actor(int(tarea["actorId"]), solo_usuarios=True)
            if not miembro or int(miembro.get("user_id", 0)) <= 0:
                conflicto("El actor de Seleccionar oferta no tiene un usuario directo autorizado")
            usuario_id = int(miembro["user_id"])
            asignado = int(tarea.get("assigned_id") or 0)
            if asignado > 0 and asignado != usuario_id:
                conflicto("La tarea Seleccionar oferta ya está asignada a otro usuario")
            try:
                if asignado <= 0:
                    await bonita_client.asignar_tarea(tarea["id"], usuario_id)
                await bonita_client.ejecutar_tarea(tarea["id"], {"seleccionInput": filas})
            except (BonitaClientError, httpx.RequestError) as exc:
                # Una respuesta perdida puede ocultar una ejecución exitosa.
                if await self._ya_confirmada(caso_id, pares):
                    return respuesta.model_copy(update={"ya_confirmada": True})
                if isinstance(exc, BonitaTaskConflictError):
                    conflicto("Bonita no pudo confirmar la tarea; actualice la emergencia y vuelva a intentar")
                raise
            return respuesta
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo consultar o confirmar la selección en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una respuesta inválida al confirmar la selección")
        finally:
            await run_in_threadpool(db.rollback)
