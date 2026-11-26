import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
import httpx
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..dto import (
    AdjudicacionRespuesta,
    EstadoFinalizacionOfertaRespuesta,
    FinalizacionOfertaRespuesta,
    OfertaConsolidada,
    OfertaItemConsolidado,
    OfertaItemRespuesta,
    OfertaListadoRespuesta,
    OfertaRespuesta,
    OfertasConsolidadas,
    OrganizacionResumen,
)
from ..integrations.email.service import notificar_adjudicacion
from ..integrations.bonita.client import BonitaClientError, BonitaTaskConflictError, bonita_client
from ..models import AporteOfertaItem, EstadoEmergencia, OfertaAyuda, OfertaItem, Organizacion
from ..repositories import (
    OfertaItemRepository,
    OfertaRepository,
    EmergenciaRepository,
    UsuarioRepository,
)
from ..schemas import OfertaActualizar, OfertaCrear
from ..dto.ofertas_dto import OfertaItemListadoRespuesta
from .emergencias_service import EmergenciaService
from .usuarios_service import OrganizacionService

NOMBRE_ROL_REPRESENTANTE_ONG = "REPRESENTANTE_ONG"
NOMBRE_TAREA_MARCAR_ACTIVIDADES_FINALIZADAS = "Marcar actividades finalizadas"
NOMBRE_TAREA_SUPERVISAR_PROYECTO = "Supervisar proyecto"
MENSAJE_OFERTAS_PENDIENTES = (
    "Todavía hay otras ofertas adjudicadas con ítems pendientes de finalización"
)


class OfertaService:
    def __init__(self) -> None:
        self._repository = OfertaRepository()
        self._items = OfertaItemRepository()
        self._emergencias = EmergenciaService()
        self._organizaciones = OrganizacionService()
        self._usuarios = UsuarioRepository()

    def listar_ofertas(
        self,
        db: Session,
        emergencia_id: Optional[int] = None,
        organizacion_id: Optional[int] = None,
    ) -> list[OfertaRespuesta]:
        ofertas = self._repository.listar(
            db,
            emergencia_id=emergencia_id,
            organizacion_id=organizacion_id,
        )
        return [OfertaRespuesta.model_validate(o) for o in ofertas]

    def obtener_oferta(
        self, db: Session, oferta_id: int
    ) -> OfertaRespuesta:
        oferta = self._obtener_oferta_entidad(db, oferta_id)
        return OfertaRespuesta.model_validate(oferta)

    def crear_oferta(self, db: Session, data: OfertaCrear) -> OfertaRespuesta:
        self._verificar_convocatoria_abierta(db, data.emergencia_id)
        self._organizaciones.obtener_organizacion(db, data.organizacion_id)
        organizaciones = self._resolver_organizaciones(
            db, data.organizacion_id, data.organizaciones_ids
        )
        items = self._validar_items(db, data.emergencia_id, data.items, organizaciones)
        oferta = OfertaAyuda(
            emergencia_id=data.emergencia_id,
            organizacion_id=data.organizacion_id,
            observaciones=data.observaciones,
        )
        oferta.items = items
        oferta.organizaciones = organizaciones
        oferta.es_conjunta = len(organizaciones) > 1
        creada = self._repository.crear(db, oferta)
        return OfertaRespuesta.model_validate(creada)

    def actualizar_oferta(
        self, db: Session, oferta_id: int, data: OfertaActualizar
    ) -> OfertaRespuesta:
        emergencia, oferta = self._bloquear_oferta(db, oferta_id)
        self._verificar_sin_confirmacion_pendiente(db, emergencia.id)
        self._verificar_convocatoria_abierta(db, oferta.emergencia_id, oferta)
        organizaciones = (
            self._resolver_organizaciones(db, oferta.organizacion_id, data.organizaciones_ids)
            if data.organizaciones_ids is not None else oferta.organizaciones
        )
        items = (self._validar_items(db, oferta.emergencia_id, data.items, organizaciones,
                                    oferta.organizacion_id)
                 if data.items is not None else None)
        if data.observaciones is not None:
            oferta.observaciones = data.observaciones
        if items is not None:
            self._repository.reemplazar_items(
                db,
                oferta,
                items,
            )
        if data.organizaciones_ids is not None:
            if items is None and {o.id for o in organizaciones} != {o.id for o in oferta.organizaciones}:
                for item in oferta.items:
                    item.aportes.clear()
            oferta.organizaciones = organizaciones
            oferta.es_conjunta = len(oferta.organizaciones) > 1
        actualizada = self._repository.actualizar(db, oferta)
        return OfertaRespuesta.model_validate(actualizada)

    def listar_ofertas_de_emergencia(
        self, db: Session, emergencia_id: int, organizacion_id: int | None = None
    ) -> list[OfertaListadoRespuesta]:
        self._emergencias.obtener_emergencia_entidad(db, emergencia_id)
        ofertas = self._repository.listar_de_emergencia(db, emergencia_id, organizacion_id)
        return [self._construir_listado(oferta) for oferta in ofertas]

    def obtener_ofertas_consolidadas(
        self, db: Session, emergencia_id: int
    ) -> OfertasConsolidadas:
        self._emergencias.obtener_emergencia_entidad(db, emergencia_id)
        ofertas = self._repository.listar_de_emergencia(db, emergencia_id)
        return OfertasConsolidadas(
            emergencia_id=emergencia_id,
            ofertas=[
                OfertaConsolidada(
                    organizacion_id=oferta.organizacion_id,
                    organizacion_nombre=(
                        oferta.organizacion.nombre
                        if oferta.organizacion
                        else ""
                    ),
                    items=[
                        OfertaItemConsolidado(
                            lote_id=item.lote_necesidad_id,
                            cantidad_ofrecida=item.cantidad_ofrecida,
                            descripcion=item.descripcion,
                        )
                        for item in oferta.items
                    ],
                )
                for oferta in ofertas
            ],
        )

    def adjudicar_oferta(
        self,
        db: Session,
        oferta_id: int,
        background_tasks: BackgroundTasks,
        para_seleccion: bool = False,
    ) -> AdjudicacionRespuesta:
        """Adjudica exclusivamente o prepara una selección explícita para Bonita.

        Sin ``para_seleccion`` conserva el contrato individual. En modo
        selección cada marca es idempotente y no adelanta la etapa local.
        Ambos recorridos toman los bloqueos en orden emergencia → oferta.
        """
        from .seleccion_ofertas_service import SeleccionOfertasService

        if para_seleccion:
            return asyncio.run(SeleccionOfertasService().preparar(db, oferta_id, self))
        emergencia, oferta = self._bloquear_oferta(db, oferta_id)
        self._validar_adjudicacion(db, emergencia, oferta, para_seleccion=False)
        seleccion = SeleccionOfertasService()
        asyncio.run(seleccion.verificar_etapa_adjudicacion(emergencia))
        asyncio.run(seleccion.verificar_validada(db, emergencia, oferta))
        return self._marcar_oferta(db, emergencia, oferta, background_tasks, False)

    def _validar_adjudicacion(self, db, emergencia, oferta, para_seleccion):
        if emergencia.estado != EstadoEmergencia.ESPERANDO_ADJUDICACION:
            raise HTTPException(
                status_code=409,
                detail="La emergencia debe estar esperando adjudicación para adjudicar una oferta",
            )
        if oferta.adjudicada_en is not None:
            if para_seleccion:
                return AdjudicacionRespuesta(
                    oferta_id=oferta.id, mensaje="Seleccionada para confirmar"
                )
            raise HTTPException(
                status_code=409,
                detail="La oferta ya fue adjudicada",
            )
        self._verificar_sin_confirmacion_pendiente(db, emergencia.id)
        otra_adjudicada = (
            db.query(OfertaAyuda)
            .filter(
                OfertaAyuda.emergencia_id == oferta.emergencia_id,
                OfertaAyuda.adjudicada_en.is_not(None),
                OfertaAyuda.id != oferta.id,
            )
            .first()
        )
        if otra_adjudicada is not None and not para_seleccion:
            raise HTTPException(
                status_code=409,
                detail="La emergencia ya tiene otra oferta adjudicada",
            )
        if not oferta.items:
            raise HTTPException(
                status_code=400,
                detail="La oferta no tiene ítems cargados",
            )

    def _marcar_oferta(self, db, emergencia, oferta, background_tasks, para_seleccion):
        if oferta.adjudicada_en is None:
            oferta.adjudicada_en = datetime.now(timezone.utc)
            if not para_seleccion:
                emergencia.estado = EstadoEmergencia.EN_PROCESO
            self._repository.actualizar(db, oferta)
        if not para_seleccion:
            self._programar_notificacion_adjudicacion(db, oferta, background_tasks)
        return AdjudicacionRespuesta(
            oferta_id=oferta.id,
            mensaje=("Seleccionada para confirmar" if para_seleccion
                     else "Notificación de adjudicación enviada"),
        )

    def _bloquear_oferta(self, db: Session, oferta_id: int):
        emergencia_id = self._repository.obtener_emergencia_id(db, oferta_id)
        if emergencia_id is None:
            raise HTTPException(status_code=404, detail="Oferta no encontrada")
        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id, bloquear=True
        )
        return emergencia, self._obtener_oferta_entidad(db, oferta_id, bloquear=True)

    def _verificar_sin_confirmacion_pendiente(self, db: Session, emergencia_id: int) -> None:
        if EmergenciaRepository().obtener_confirmacion(db, emergencia_id) is not None:
            raise HTTPException(
                status_code=409,
                detail="La selección está pendiente de confirmación; vuelva a confirmar la selección antes de modificar sus ofertas",
            )

    def _programar_notificacion_adjudicacion(
        self,
        db: Session,
        oferta: OfertaAyuda,
        background_tasks: BackgroundTasks,
    ) -> None:
        """Agenda el aviso por email de la adjudicacion a la ONG.

        Los destinatarios y los datos de la oferta se resuelven aca, con la
        sesion de la request todavia abierta. La background task recibe solo
        primitivos porque su sesion ya fue cerrada.
        """
        background_tasks.add_task(
            notificar_adjudicacion, *self._datos_notificacion_adjudicacion(db, oferta)
        )

    def _datos_notificacion_adjudicacion(self, db: Session, oferta: OfertaAyuda,
                                        fecha_hora_adjudicacion=None) -> tuple:
        """Resuelve los mismos destinatarios y datos para ambos caminos de aviso."""
        organizacion = self._organizaciones.obtener_organizacion_entidad(
            db, oferta.organizacion_id
        )
        representantes = self._usuarios.listar_por_rol_nombre(
            db,
            NOMBRE_ROL_REPRESENTANTE_ONG,
            organizacion_id=oferta.organizacion_id,
        )
        destinatarios = set()
        if organizacion.email:
            destinatarios.add(organizacion.email)
        for usuario in representantes:
            destinatarios.add(usuario.email)
        lotes_adjudicados = [
            item.lote_necesidad.tipo for item in oferta.items
        ]
        return (
            list(destinatarios),
            oferta.id,
            oferta.emergencia_id,
            oferta.emergencia.zona_afectada,
            lotes_adjudicados,
            fecha_hora_adjudicacion or datetime.now(timezone.utc),
        )

    async def finalizar_item(
        self, db: Session, oferta_id: int, item_id: int
    ) -> OfertaItemRespuesta:
        """Cierra la actividad del ítem indicado (etapa 7 del flujo).

        Es idempotente: si el ítem ya estaba finalizado se devuelve con la
        fecha original, sin reescribirla.
        """
        try:
            respuesta, adjudicada = await run_in_threadpool(
                self._finalizar_item_local, db, oferta_id, item_id
            )
            if not adjudicada:
                return respuesta
            # actualizar confirma el ítem y libera el bloqueo inicial. Volvemos a
            # tomarlo para serializar la comprobación global y el intento Bonita.
            emergencia, oferta = await run_in_threadpool(
                self._bloquear_oferta, db, oferta_id
            )
            if oferta.adjudicada_en is not None and await run_in_threadpool(
                self._adjudicadas_finalizadas, db, emergencia.id, True
            ):
                try:
                    await self._ejecutar_tarea_ong(emergencia, oferta)
                except BonitaTaskConflictError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail="Bonita rechazó la finalización de la ONG; vuelva a intentarlo",
                    ) from exc
                except (BonitaClientError, httpx.RequestError) as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="No se pudo procesar en Bonita la finalización de la ONG",
                    ) from exc
                except (KeyError, TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="Bonita devolvió una respuesta inválida al finalizar la ONG",
                    ) from exc
            return respuesta
        finally:
            await run_in_threadpool(db.rollback)

    def _finalizar_item_local(
        self, db: Session, oferta_id: int, item_id: int
    ) -> tuple[OfertaItemRespuesta, bool]:
        """Guarda la actividad antes de intentar avanzar el caso externo."""
        _, oferta = self._bloquear_oferta(db, oferta_id)
        item = next(
            (item for item in oferta.items if item.id == item_id), None
        )
        if item is None:
            raise HTTPException(
                status_code=404, detail="Ítem no encontrado"
            )
        if item.finalizado_en is None:
            item.finalizado_en = datetime.now(timezone.utc)
            self._repository.actualizar(db, oferta)
        return OfertaItemRespuesta.model_validate(item), oferta.adjudicada_en is not None

    def _adjudicadas_finalizadas(
        self, db: Session, emergencia_id: int, bloquear: bool = False
    ) -> bool:
        """Exige al menos un ítem y ninguna actividad pendiente por adjudicada."""
        adjudicadas = [
            oferta for oferta in self._repository.listar_de_emergencia(
                db, emergencia_id, bloquear=bloquear
            ) if oferta.adjudicada_en is not None
        ]
        return bool(adjudicadas) and all(
            oferta.items and all(item.finalizado_en is not None for item in oferta.items)
            for oferta in adjudicadas
        )

    async def _ejecutar_tarea_ong(self, emergencia, oferta) -> None:
        """Completa la tarea cuando cerraron todas las ofertas adjudicadas."""
        await self._ejecutar_tarea_humana(
            emergencia,
            NOMBRE_TAREA_MARCAR_ACTIVIDADES_FINALIZADAS,
            tolerar_tarea_no_disponible=True,
        )

    async def _ejecutar_tarea_humana(
        self,
        emergencia,
        nombre_tarea: str,
        *,
        tolerar_tarea_no_disponible: bool = False,
    ) -> bool:
        """Ejecuta una tarea Bonita por nombre sin repetirla.

        Devuelve ``False`` si la tarea todavía no fue creada y esa ausencia es
        tolerable para el caso de uso. Si ya fue archivada como completada,
        devuelve ``True`` sin volver a ejecutarla.
        """
        if not emergencia.bonita_case_id:
            raise BonitaClientError("La emergencia no tiene un caso de Bonita asociado")
        caso_id = int(emergencia.bonita_case_id)
        if caso_id <= 0:
            raise ValueError("El identificador del caso de Bonita no es válido")

        tarea = await bonita_client.obtener_tarea_pendiente(
            caso_id, nombre_tarea
        )
        if tarea is None:
            completada = await bonita_client.tarea_completada_por_nombre(
                caso_id, nombre_tarea
            )
            if completada:
                return True
            if tolerar_tarea_no_disponible:
                return False
            raise BonitaTaskConflictError(
                f"La tarea Bonita '{nombre_tarea}' aún no está habilitada"
            )
        if (
            not isinstance(tarea, dict)
            or str(tarea.get("caseId")) != str(caso_id)
            or tarea.get("name") != nombre_tarea
        ):
            raise ValueError(f"Bonita devolvió una tarea inválida para '{nombre_tarea}'")

        asignado = int(tarea.get("assigned_id") or 0)
        try:
            if asignado <= 0:
                actor_id = int(tarea["actorId"])
                miembro = await bonita_client.obtener_miembro_actor(
                    actor_id, solo_usuarios=True
                )
                if not miembro or int(miembro.get("user_id", 0)) <= 0:
                    raise BonitaClientError(
                        f"La tarea '{nombre_tarea}' no tiene un usuario autorizado"
                    )
                usuario_id = int(miembro["user_id"])
                await bonita_client.asignar_tarea(tarea["id"], usuario_id)
            await bonita_client.ejecutar_tarea(tarea["id"])
        except (BonitaClientError, httpx.RequestError):
            if await bonita_client.tarea_completada_por_nombre(
                caso_id, nombre_tarea
            ):
                return True
            raise
        return True

    async def finalizar_oferta(
        self, db: Session, oferta_id: int
    ) -> FinalizacionOfertaRespuesta:
        """Ejecuta la supervisión del coordinador y continúa la liberación."""
        try:
            emergencia, oferta = await run_in_threadpool(
                self._bloquear_oferta, db, oferta_id
            )
            if oferta.adjudicada_en is None:
                raise HTTPException(status_code=409, detail="La oferta no está adjudicada")
            if not oferta.items:
                raise HTTPException(status_code=409, detail="La oferta adjudicada no tiene ítems")
            if any(item.finalizado_en is None for item in oferta.items):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "codigo": "TAREA_NO_HABILITADA",
                        "habilitada": False,
                        "tarea": NOMBRE_TAREA_SUPERVISAR_PROYECTO,
                        "mensaje": (
                            "La tarea 'Supervisar proyecto' aún no está habilitada: "
                            "todos los ítems de la oferta adjudicada deben estar finalizados"
                        ),
                    },
                )
            if not await run_in_threadpool(
                self._adjudicadas_finalizadas, db, emergencia.id, True
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "codigo": "TAREA_NO_HABILITADA",
                        "habilitada": False,
                        "tarea": NOMBRE_TAREA_SUPERVISAR_PROYECTO,
                        "mensaje": MENSAJE_OFERTAS_PENDIENTES,
                    },
                )
            if not emergencia.bonita_case_id:
                raise HTTPException(status_code=409, detail="La emergencia no tiene un caso de Bonita asociado")
            try:
                caso_id = int(emergencia.bonita_case_id)
                if caso_id <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise HTTPException(status_code=409, detail="El identificador del caso de Bonita no es válido")

            try:
                await self._ejecutar_tarea_humana(
                    emergencia,
                    NOMBRE_TAREA_SUPERVISAR_PROYECTO,
                )
            except BonitaTaskConflictError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "codigo": "TAREA_NO_HABILITADA",
                        "habilitada": False,
                        "tarea": NOMBRE_TAREA_SUPERVISAR_PROYECTO,
                        "mensaje": str(exc),
                    },
                ) from exc
            return FinalizacionOfertaRespuesta(
                oferta_id=oferta.id,
                estado="finalizada",
                ya_finalizada=True,
                tarea_bonita=NOMBRE_TAREA_SUPERVISAR_PROYECTO,
                mensaje="Se registró el cierre de la oferta.",
            )
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(status_code=503, detail="No se pudo completar la oferta en Bonita")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=503, detail="Bonita devolvió una respuesta inválida al finalizar la oferta")
        finally:
            await run_in_threadpool(db.rollback)

    async def consultar_estado_finalizacion(
        self, db: Session, oferta_id: int
    ) -> EstadoFinalizacionOfertaRespuesta:
        """Consulta si Bonita habilitó la finalización de una oferta adjudicada."""
        oferta = await run_in_threadpool(self._obtener_oferta_entidad, db, oferta_id)
        items_finalizados = bool(oferta.items) and all(
            item.finalizado_en is not None for item in oferta.items
        )
        estado = {
            "oferta_id": oferta.id,
            "items_finalizados": items_finalizados,
            "tarea_ong_completada": False,
            "supervisar_proyecto_pendiente": False,
            "habilitada": False,
        }

        if oferta.adjudicada_en is None:
            return EstadoFinalizacionOfertaRespuesta(
                **estado, mensaje="La oferta no está adjudicada"
            )
        if not oferta.items:
            return EstadoFinalizacionOfertaRespuesta(
                **estado, mensaje="La oferta adjudicada no tiene ítems"
            )
        if not items_finalizados:
            return EstadoFinalizacionOfertaRespuesta(
                **estado,
                mensaje=(
                    "La oferta adjudicada tiene ítems pendientes de finalización"
                ),
            )
        if not await run_in_threadpool(
            self._adjudicadas_finalizadas, db, oferta.emergencia_id
        ):
            return EstadoFinalizacionOfertaRespuesta(
                **estado, mensaje=MENSAJE_OFERTAS_PENDIENTES
            )
        if not oferta.emergencia.bonita_case_id:
            return EstadoFinalizacionOfertaRespuesta(
                **estado,
                mensaje="La oferta adjudicada no tiene un caso de Bonita asociado",
            )

        try:
            caso_id = int(oferta.emergencia.bonita_case_id)
            if caso_id <= 0:
                raise ValueError
            tarea_ong_completada = await bonita_client.tarea_completada_por_nombre(
                caso_id, NOMBRE_TAREA_MARCAR_ACTIVIDADES_FINALIZADAS
            )
            if type(tarea_ong_completada) is not bool:
                raise ValueError("Bonita devolvió un estado inválido")
            estado["tarea_ong_completada"] = tarea_ong_completada
            if not tarea_ong_completada:
                return EstadoFinalizacionOfertaRespuesta(
                    **estado,
                    mensaje=(
                        "La tarea 'Marcar actividades finalizadas' aún no está "
                        "completada en Bonita"
                    ),
                )

            tarea_supervisar = await bonita_client.obtener_tarea_pendiente(
                caso_id, NOMBRE_TAREA_SUPERVISAR_PROYECTO
            )
            if tarea_supervisar is not None:
                if (
                    not isinstance(tarea_supervisar, dict)
                    or str(tarea_supervisar.get("caseId")) != str(caso_id)
                    or tarea_supervisar.get("name") != NOMBRE_TAREA_SUPERVISAR_PROYECTO
                ):
                    raise ValueError("Bonita devolvió una tarea inválida")
                estado["supervisar_proyecto_pendiente"] = True
        except (BonitaClientError, httpx.RequestError) as exc:
            raise HTTPException(
                status_code=503,
                detail="No se pudo consultar el estado de la oferta en Bonita",
            ) from exc
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Bonita devolvió una respuesta inválida al consultar la finalización",
            ) from exc

        if estado["supervisar_proyecto_pendiente"]:
            estado["habilitada"] = True
            mensaje = "La tarea 'Supervisar proyecto' está habilitada"
        else:
            mensaje = "La tarea 'Supervisar proyecto' aún no está disponible en Bonita"
        return EstadoFinalizacionOfertaRespuesta(**estado, mensaje=mensaje)

    def existe_referencia_a_lote(self, db: Session, lote_id: int) -> bool:
        """Informa si alguna oferta usa el lote indicado."""
        return self._items.existe_referencia_a_lote(db, lote_id)

    def _obtener_oferta_entidad(
        self, db: Session, oferta_id: int, bloquear: bool = False
    ) -> OfertaAyuda:
        oferta = self._repository.obtener_por_id(db, oferta_id, bloquear)
        if oferta is None:
            raise HTTPException(status_code=404, detail="Oferta no encontrada")
        return oferta

    def _verificar_convocatoria_abierta(
        self,
        db: Session,
        emergencia_id: int,
        oferta: OfertaAyuda | None = None,
    ) -> None:
        """Implementa la ventana de tiempo de la convocatoria del enunciado.

        Solo se pueden cargar o modificar ofertas mientras la emergencia esté
        esperando ofertas; en cualquier otro estado la convocatoria está
        cerrada.
        """
        if oferta is not None and oferta.adjudicada_en is not None:
            raise HTTPException(
                status_code=409,
                detail="La oferta adjudicada no se puede modificar",
            )

        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id
        )
        if emergencia.estado != EstadoEmergencia.ESPERA_OFERTAS:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La convocatoria está cerrada: no se pueden cargar ni "
                    "modificar ofertas"
                ),
            )

    def _resolver_organizaciones(
        self, db: Session, lider_id: int, socias_ids: list[int]
    ) -> list[Organizacion]:
        """Arma la lista de participantes de la oferta (lider + socias).

        La ONG lider siempre queda incluida y los ids repetidos se descartan,
        de modo que `es_conjunta` se deduce del largo de la lista.
        """
        ids_ordenados = [lider_id]
        for organizacion_id in socias_ids:
            if organizacion_id not in ids_ordenados:
                ids_ordenados.append(organizacion_id)
        return [
            self._organizaciones.obtener_organizacion_entidad(
                db, organizacion_id
            )
            for organizacion_id in ids_ordenados
        ]

    def _validar_items(self, db: Session, emergencia_id: int, items,
                       organizaciones=None, responsable_id=None) -> list[OfertaItem]:
        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id, bloquear=True
        )
        lotes_validos = {lote.id for lote in emergencia.lotes}
        vistos = set()
        nuevos = []
        participantes = {o.id for o in organizaciones or []}
        if responsable_id is not None:
            participantes.add(responsable_id)
        for item in items:
            if item.lote_necesidad_id not in lotes_validos:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"El lote {item.lote_necesidad_id} no pertenece a "
                        f"la emergencia {emergencia_id}"
                    ),
                )
            if item.lote_necesidad_id in vistos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Lote duplicado en la oferta: {item.lote_necesidad_id}",
                )
            vistos.add(item.lote_necesidad_id)
            nuevo = OfertaItem(**item.model_dump(exclude={"aportes"}))
            if item.aportes is not None:
                ids = [aporte.organizacion_id for aporte in item.aportes]
                if len(ids) != len(set(ids)) or not set(ids).issubset(participantes):
                    raise HTTPException(400, f"Los aportes del lote {item.lote_necesidad_id} deben pertenecer a participantes sin duplicados")
                if sum(aporte.cantidad for aporte in item.aportes) != item.cantidad_ofrecida:
                    raise HTTPException(400, f"Los aportes del lote {item.lote_necesidad_id} deben sumar la cantidad ofrecida")
                nuevo.aportes = [AporteOfertaItem(**aporte.model_dump()) for aporte in item.aportes]
            nuevos.append(nuevo)
        return nuevos

    @staticmethod
    def _construir_listado(oferta: OfertaAyuda) -> OfertaListadoRespuesta:
        return OfertaListadoRespuesta(
            id=oferta.id,
            emergencia_id=oferta.emergencia_id,
            organizacion_id=oferta.organizacion_id,
            organizacion_nombre=(
                oferta.organizacion.nombre if oferta.organizacion else None
            ),
            observaciones=oferta.observaciones,
            fecha_hora_oferta=oferta.fecha_hora_oferta,
            es_conjunta=oferta.es_conjunta,
            adjudicada_en=oferta.adjudicada_en,
            organizaciones=[
                OrganizacionResumen(
                    id=organizacion.id, nombre=organizacion.nombre
                )
                for organizacion in oferta.organizaciones
            ],
            items=[
                OfertaItemListadoRespuesta(
                    id=item.id,
                    lote_necesidad_id=item.lote_necesidad_id,
                    cantidad_ofrecida=item.cantidad_ofrecida,
                    descripcion=item.descripcion,
                    finalizado_en=item.finalizado_en,
                    aportes=item.aportes,
                )
                for item in oferta.items
            ],
        )
