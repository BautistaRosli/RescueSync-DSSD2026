from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from ..dto import (
    AdjudicacionRespuesta,
    OfertaConsolidada,
    OfertaItemConsolidado,
    OfertaItemRespuesta,
    OfertaListadoRespuesta,
    OfertaRespuesta,
    OfertasConsolidadas,
    OrganizacionResumen,
)
from ..integrations.email.service import notificar_adjudicacion
from ..models import OfertaAyuda, OfertaItem, Organizacion
from ..repositories import (
    OfertaItemRepository,
    OfertaRepository,
    UsuarioRepository,
)
from ..schemas import OfertaActualizar, OfertaCrear
from .emergencias_service import EmergenciaService
from .usuarios_service import OrganizacionService

NOMBRE_ROL_REPRESENTANTE_ONG = "REPRESENTANTE_ONG"


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
        self._organizaciones.obtener_organizacion(db, data.organizacion_id)
        items = self._validar_items(db, data.emergencia_id, data.items)
        organizaciones = self._resolver_organizaciones(
            db, data.organizacion_id, data.organizaciones_ids
        )
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
        oferta = self._obtener_oferta_entidad(db, oferta_id, bloquear=True)
        if data.observaciones is not None:
            oferta.observaciones = data.observaciones
        if data.items is not None:
            self._repository.reemplazar_items(
                db,
                oferta,
                self._validar_items(db, oferta.emergencia_id, data.items),
            )
        if data.organizaciones_ids is not None:
            oferta.organizaciones = self._resolver_organizaciones(
                db, oferta.organizacion_id, data.organizaciones_ids
            )
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
    ) -> AdjudicacionRespuesta:
        """Adjudica una oferta y agenda el aviso por email a la ONG."""
        oferta = self._obtener_oferta_entidad(db, oferta_id)
        if not oferta.items:
            raise HTTPException(
                status_code=400,
                detail="La oferta no tiene ítems cargados",
            )
        self._programar_notificacion_adjudicacion(db, oferta, background_tasks)
        return AdjudicacionRespuesta(
            oferta_id=oferta_id,
            mensaje="Notificación de adjudicación enviada",
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
        background_tasks.add_task(
            notificar_adjudicacion,
            list(destinatarios),
            oferta.id,
            oferta.emergencia_id,
            oferta.emergencia.zona_afectada,
            lotes_adjudicados,
            datetime.now(timezone.utc),
        )

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

    def _validar_items(self, db: Session, emergencia_id: int, items) -> list[OfertaItem]:
        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id, bloquear=True
        )
        lotes_validos = {lote.id for lote in emergencia.lotes}
        vistos = set()
        nuevos = []
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
            nuevos.append(OfertaItem(**item.model_dump()))
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
            organizaciones=[
                OrganizacionResumen(
                    id=organizacion.id, nombre=organizacion.nombre
                )
                for organizacion in oferta.organizaciones
            ],
            items=[
                OfertaItemRespuesta(
                    id=item.id,
                    lote_necesidad_id=item.lote_necesidad_id,
                    cantidad_ofrecida=item.cantidad_ofrecida,
                    descripcion=item.descripcion,
                )
                for item in oferta.items
            ],
        )
