"""Completa Evaluar proyecto sin adelantarse a su conector ON_FINISH."""

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..integrations.bonita.client import BonitaClientError, BonitaTaskConflictError, bonita_client
from ..models import EstadoEmergencia
from ..schemas.emergencias_schema import (
    EvaluacionProyectoConSeleccionRespuesta, EvaluacionProyectoEntrada, EvaluacionProyectoRespuesta,
)
from .curso_accion_service import CursoAccionService
from .emergencias_service import EmergenciaService

NOMBRE_TAREA = "Evaluar proyecto"


class EvaluacionProyectoService:
    async def consultar(
        self, db: Session, emergencia_id: int, incluir_seleccion: bool = False,
    ) -> EvaluacionProyectoRespuesta:
        try:
            caso_id = await run_in_threadpool(self._obtener_caso, db, emergencia_id)
            tarea_id = None
            if caso_id is not None:
                tarea = await bonita_client.obtener_tarea_pendiente(caso_id, NOMBRE_TAREA)
                if tarea is not None:
                    self._validar_identidad(tarea, caso_id)
                    if tarea.get("state") == "ready":
                        tarea_id = self._identificador(tarea["id"])
            if incluir_seleccion:
                seleccion_lista = False
                if caso_id is not None and tarea_id is None:
                    seleccion = await bonita_client.obtener_tarea_pendiente(caso_id, "Seleccionar oferta")
                    if seleccion is not None:
                        self._validar_identidad(seleccion, caso_id, "Seleccionar oferta")
                        self._identificador(seleccion["id"])
                        seleccion_lista = seleccion.get("state") == "ready"
                return EvaluacionProyectoConSeleccionRespuesta(
                    tarea_id=tarea_id, seleccion_oferta_lista=seleccion_lista,
                )
            return EvaluacionProyectoRespuesta(tarea_id=tarea_id)
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo consultar la evaluación en Bonita") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HTTPException(503, "Bonita devolvió una respuesta inválida de evaluación") from None

    async def ejecutar(
        self, db: Session, emergencia_id: int, data: EvaluacionProyectoEntrada
    ) -> EvaluacionProyectoRespuesta:
        try:
            caso_id = await run_in_threadpool(self._obtener_caso, db, emergencia_id, data.accion)
            if await bonita_client.tarea_completada(caso_id, str(data.tarea_id), NOMBRE_TAREA):
                raise HTTPException(409, "La tarea de evaluación ya fue completada")
            tarea = await bonita_client.obtener_tarea_pendiente(caso_id, NOMBRE_TAREA)
            if tarea is None or self._validar_tarea(tarea, caso_id) != data.tarea_id:
                raise HTTPException(409, "La tarea de evaluación ya no está pendiente en este caso")
            asignacion = tarea.get("assigned_id")
            asignado = self._identificador(0 if asignacion in (None, "") else asignacion, permitir_cero=True)
            if asignado == 0:
                actor_id = self._identificador(tarea["actorId"])
                miembro = await bonita_client.obtener_miembro_actor(actor_id, solo_usuarios=True)
                if not miembro:
                    raise HTTPException(503, "El actor de Evaluar proyecto no tiene un usuario directo autorizado")
                asignado = self._identificador(miembro.get("user_id"))
                await bonita_client.asignar_tarea(data.tarea_id, asignado)
            # Relee la fase sin bloquear y libera también la transacción de
            # autenticación. ON_FINISH necesita bloquear esta misma emergencia.
            caso_actual = await run_in_threadpool(self._obtener_caso, db, emergencia_id, data.accion)
            if caso_actual != caso_id:
                raise HTTPException(409, "El caso de la emergencia cambió durante la evaluación")
            # No reintentar ante respuesta perdida: el motor arbitra por ID.
            # El cliente debe consultar el mismo caso antes de otra decisión.
            await bonita_client.ejecutar_tarea(data.tarea_id, {"accionInput": data.accion})
            return EvaluacionProyectoRespuesta(tarea_id=data.tarea_id)
        except BonitaTaskConflictError:
            raise HTTPException(409, "La tarea de evaluación cambió o Bonita rechazó la decisión") from None
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo confirmar la evaluación en Bonita; consulte su estado antes de intentar otra vez") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HTTPException(503, "Bonita devolvió una respuesta inválida de evaluación") from None

    @staticmethod
    def _obtener_caso(db: Session, emergencia_id: int, accion: str | None = None) -> int | None:
        try:
            emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id)
            if (emergencia.estado != EstadoEmergencia.ESPERANDO_ADJUDICACION
                    or not emergencia.publicada or not emergencia.bonita_case_id):
                if accion is not None:
                    raise HTTPException(409, "La emergencia no está esperando la decisión de evaluación")
                return None
            if accion is not None and accion != "CONTINUAR_PARCIAL":
                CursoAccionService.validar_retroceso(db, emergencia_id)
            return EvaluacionProyectoService._identificador(emergencia.bonita_case_id)
        except SQLAlchemyError:
            raise HTTPException(503, "No se pudo consultar el estado de la emergencia") from None
        finally:
            db.rollback()

    @staticmethod
    def _identificador(valor, permitir_cero: bool = False) -> int:
        if type(valor) is not int and not (isinstance(valor, str) and valor.isdecimal()):
            raise ValueError("Identificador inválido de Bonita")
        identificador = int(valor)
        if identificador < (0 if permitir_cero else 1):
            raise ValueError("Identificador inválido de Bonita")
        return identificador

    @classmethod
    def _validar_tarea(cls, tarea: dict, caso_id: int) -> int:
        cls._validar_identidad(tarea, caso_id)
        if tarea.get("state") != "ready":
            raise HTTPException(409, "La tarea no corresponde a Evaluar proyecto pendiente de este caso")
        return cls._identificador(tarea["id"])

    @staticmethod
    def _validar_identidad(tarea: dict, caso_id: int, nombre_tarea: str = NOMBRE_TAREA) -> None:
        if str(tarea.get("caseId")) != str(caso_id) or tarea.get("name") != nombre_tarea:
            raise HTTPException(409, f"La tarea no corresponde a {nombre_tarea} pendiente de este caso")
