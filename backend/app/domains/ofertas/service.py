from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..emergencias.service import EmergenciaService
from ..usuarios.service import OrganizacionService
from .models import OfertaAyuda, OfertaItem
from .repository import OfertaItemRepository, OfertaRepository
from .schemas import OfertaActualizar, OfertaCrear


class OfertaService:
    def __init__(self) -> None:
        self._repository = OfertaRepository()
        self._items = OfertaItemRepository()
        self._emergencias = EmergenciaService()
        self._organizaciones = OrganizacionService()

    def listar_ofertas(
        self,
        db: Session,
        emergencia_id: Optional[int] = None,
        organizacion_id: Optional[int] = None,
    ):
        return self._repository.listar(
            db,
            emergencia_id=emergencia_id,
            organizacion_id=organizacion_id,
        )

    def obtener_oferta(self, db: Session, oferta_id: int) -> OfertaAyuda:
        oferta = self._repository.obtener_por_id(db, oferta_id)
        if oferta is None:
            raise HTTPException(status_code=404, detail="Oferta no encontrada")
        return oferta

    def crear_oferta(self, db: Session, data: OfertaCrear) -> OfertaAyuda:
        self._organizaciones.obtener_organizacion(db, data.organizacion_id)
        items = self._validar_items(db, data.emergencia_id, data.items)
        oferta = OfertaAyuda(
            emergencia_id=data.emergencia_id,
            organizacion_id=data.organizacion_id,
            observaciones=data.observaciones,
        )
        oferta.items = items
        return self._repository.crear(db, oferta)

    def actualizar_oferta(
        self, db: Session, oferta_id: int, data: OfertaActualizar
    ) -> OfertaAyuda:
        oferta = self.obtener_oferta(db, oferta_id)
        if data.observaciones is not None:
            oferta.observaciones = data.observaciones
        if data.items is not None:
            oferta.items = self._validar_items(
                db, oferta.emergencia_id, data.items
            )
        return self._repository.actualizar(db, oferta)

    def listar_ofertas_de_emergencia(
        self, db: Session, emergencia_id: int
    ) -> list[dict]:
        self._emergencias.obtener_emergencia(db, emergencia_id)
        ofertas = self._repository.listar_de_emergencia(db, emergencia_id)
        return [self._serializar_listado(oferta) for oferta in ofertas]

    def obtener_ofertas_consolidadas(
        self, db: Session, emergencia_id: int
    ) -> dict:
        self._emergencias.obtener_emergencia(db, emergencia_id)
        ofertas = self._repository.listar_de_emergencia(db, emergencia_id)
        return {
            "emergencia_id": emergencia_id,
            "ofertas": [
                {
                    "organizacion_id": oferta.organizacion_id,
                    "organizacion_nombre": (
                        oferta.organizacion.nombre
                        if oferta.organizacion
                        else ""
                    ),
                    "items": [
                        {
                            "lote_id": item.lote_necesidad_id,
                            "cantidad_ofrecida": item.cantidad_ofrecida,
                            "descripcion": item.descripcion,
                        }
                        for item in oferta.items
                    ],
                }
                for oferta in ofertas
            ],
        }

    def existe_referencia_a_lote(self, db: Session, lote_id: int) -> bool:
        """Informa si alguna oferta usa el lote indicado."""
        return self._items.existe_referencia_a_lote(db, lote_id)

    def _validar_items(self, db: Session, emergencia_id: int, items) -> list[OfertaItem]:
        emergencia = self._emergencias.obtener_emergencia(db, emergencia_id)
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
    def _serializar_listado(oferta: OfertaAyuda) -> dict:
        return {
            "id": oferta.id,
            "emergencia_id": oferta.emergencia_id,
            "organizacion_id": oferta.organizacion_id,
            "organizacion_nombre": (
                oferta.organizacion.nombre if oferta.organizacion else None
            ),
            "observaciones": oferta.observaciones,
            "fecha_hora_oferta": oferta.fecha_hora_oferta,
            "items": [
                {
                    "id": item.id,
                    "lote_necesidad_id": item.lote_necesidad_id,
                    "cantidad_ofrecida": item.cantidad_ofrecida,
                    "descripcion": item.descripcion,
                }
                for item in oferta.items
            ],
        }
