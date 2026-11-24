"""Sincroniza las decisiones de Evaluar proyecto con la convocatoria local."""

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dto import EmergenciaRespuesta
from ..integrations.bonita.client import BonitaClientError, bonita_client
from ..models import CursoAccionEmergencia, EstadoEmergencia, OfertaAyuda
from ..repositories import EmergenciaRepository
from .emergencias_service import EmergenciaService


class CursoAccionService:
    def aplicar(self, db: Session, emergencia_id: int, accion: str) -> None:
        try:
            emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id, bloquear=True)
            estado, publicada = {
                "REABRIR": (EstadoEmergencia.ESPERA_OFERTAS, True),
                "REFORMULAR": (EstadoEmergencia.ESPERA_LOTES, False),
                "CONTINUAR_PARCIAL": (EstadoEmergencia.ESPERANDO_ADJUDICACION, True),
            }[accion]
            if not emergencia.bonita_case_id:
                raise HTTPException(409, "La emergencia no tiene un caso Bonita iniciado")
            anterior = db.get(CursoAccionEmergencia, emergencia_id, populate_existing=True)
            if (anterior is not None and anterior.accion == accion
                    and anterior.caso_id == emergencia.bonita_case_id
                    and emergencia.estado == estado and emergencia.publicada == publicada):
                return
            if (anterior is not None and anterior.accion == "CONTINUAR_PARCIAL"
                    and anterior.caso_id == emergencia.bonita_case_id):
                raise HTTPException(409, "La evaluación ya confirmó otro curso de acción")
            if emergencia.estado != EstadoEmergencia.ESPERANDO_ADJUDICACION or not emergencia.publicada:
                raise HTTPException(409, "La emergencia no está esperando la decisión de evaluación")
            if accion != "CONTINUAR_PARCIAL":
                seleccion = EmergenciaRepository().obtener_confirmacion(db, emergencia_id)
                adjudicada = db.query(OfertaAyuda.id).filter(
                    OfertaAyuda.emergencia_id == emergencia_id,
                    OfertaAyuda.adjudicada_en.is_not(None),
                ).first()
                if seleccion is not None or adjudicada is not None:
                    raise HTTPException(409, "La emergencia tiene una selección en curso; no se puede retroceder")
            emergencia.estado = estado
            emergencia.publicada = publicada
            # fecha_publicacion conserva la publicación histórica al reformular.
            if anterior is None:
                anterior = CursoAccionEmergencia(emergencia_id=emergencia_id)
                db.add(anterior)
            anterior.accion = accion
            anterior.caso_id = emergencia.bonita_case_id
            anterior.tarea_publicacion_id = None
            anterior.publicacion_completada = False
            db.commit()
        except SQLAlchemyError:
            raise HTTPException(503, "No se pudo guardar el curso de acción; vuelva a intentar") from None
        finally:
            db.rollback()

    async def publicar(self, db: Session, emergencia_id: int) -> EmergenciaRespuesta:
        """El primer ciclo mantiene su barrera al crear; los siguientes, al publicar.

        Persiste la identidad de la tarea antes de ejecutarla. Un reintento
        sólo reconcilia esa tarea archivada, nunca otra vuelta del mismo caso.
        """
        try:
            emergencia = await run_in_threadpool(
                EmergenciaService().obtener_emergencia_entidad, db, emergencia_id, bloquear=True
            )
            curso = db.get(CursoAccionEmergencia, emergencia_id, populate_existing=True)
            pendiente = curso.tarea_publicacion_id if curso is not None else None
            reformulada = curso is not None and curso.accion == "REFORMULAR"
            if emergencia.publicada:
                if (pendiente and curso.publicacion_completada
                        and curso.caso_id == emergencia.bonita_case_id
                        and emergencia.estado == EstadoEmergencia.ESPERA_OFERTAS):
                    return EmergenciaRespuesta.model_validate(emergencia)
                raise HTTPException(409, "La emergencia ya fue publicada")
            if not reformulada:
                return await run_in_threadpool(EmergenciaService().publicar_emergencia, db, emergencia_id)
            if emergencia.estado != EstadoEmergencia.ESPERA_LOTES or not emergencia.bonita_case_id:
                raise HTTPException(409, "La emergencia no está esperando la publicación de lotes reformulados")
            if not emergencia.lotes:
                raise HTTPException(400, "La emergencia no tiene lotes de necesidad cargados: no se puede publicar")
            caso_id = int(emergencia.bonita_case_id)
            if curso is None or curso.accion != "REFORMULAR" or curso.caso_id != str(caso_id):
                raise HTTPException(409, "No hay una reformulación registrada para este caso")
            if pendiente is None:
                tarea = await bonita_client.obtener_tarea_pendiente(caso_id, "Generar lotes")
                if tarea is None:
                    raise HTTPException(409, "El caso aún no tiene pendiente la tarea Generar lotes")
                self._validar_tarea(tarea, caso_id)
                curso.tarea_publicacion_id = str(tarea["id"])
                # Este commit libera el lock: reentrar recarga el estado y evita
                # ejecutar usando una fotografía anterior a otro publicador.
                await run_in_threadpool(db.commit)
                return await self.publicar(db, emergencia_id)
            if not await bonita_client.tarea_completada(caso_id, pendiente, "Generar lotes"):
                tarea = await bonita_client.obtener_tarea_pendiente(caso_id, "Generar lotes")
                if tarea is None:
                    raise HTTPException(409, "La publicación aún no está confirmada en Bonita; vuelva a intentar")
                self._validar_tarea(tarea, caso_id)
                if str(tarea["id"]) != pendiente:
                    raise HTTPException(409, "La tarea pendiente no coincide con la publicación iniciada")
                asignado = int(tarea.get("assigned_id") or 0)
                if asignado <= 0:
                    miembro = await bonita_client.obtener_miembro_actor(int(tarea["actorId"]), solo_usuarios=True)
                    if not miembro or int(miembro.get("user_id", 0)) <= 0:
                        raise HTTPException(503, "El actor de Generar lotes no tiene un usuario directo autorizado")
                    asignado = int(miembro["user_id"])
                try:
                    if not int(tarea.get("assigned_id") or 0):
                        await bonita_client.asignar_tarea(pendiente, asignado)
                    await bonita_client.ejecutar_tarea(pendiente)
                except (BonitaClientError, httpx.RequestError):
                    if not await bonita_client.tarea_completada(caso_id, pendiente, "Generar lotes"):
                        raise
            curso.publicacion_completada = True
            # Reutiliza la publicación local existente y conserva su respuesta.
            return await run_in_threadpool(EmergenciaService().publicar_emergencia, db, emergencia_id)
        except SQLAlchemyError:
            raise HTTPException(503, "No se pudo guardar la publicación local; vuelva a intentar") from None
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo completar la publicación en Bonita; vuelva a intentar") from None
        except (KeyError, TypeError, ValueError):
            raise HTTPException(503, "Bonita devolvió una respuesta inválida al publicar") from None
        finally:
            await run_in_threadpool(db.rollback)

    @staticmethod
    def _validar_tarea(tarea: dict, caso_id: int) -> None:
        if (str(tarea.get("caseId")) != str(caso_id) or tarea.get("name") != "Generar lotes"
                or tarea.get("state") != "ready"):
            raise HTTPException(409, "La tarea no corresponde a Generar lotes pendiente de este caso")
