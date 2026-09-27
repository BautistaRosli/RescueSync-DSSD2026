from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..models import OfertaAyuda, OfertaItem, Organizacion


class OfertaItemRepository:
    def existe_referencia_a_lote(self, db: Session, lote_id: int) -> bool:
        return (
            db.query(OfertaItem.id)
            .filter(OfertaItem.lote_necesidad_id == lote_id)
            .first()
            is not None
        )


class OfertaRepository:
    def _consulta_con_relaciones(self, db: Session):
        return db.query(OfertaAyuda).options(
            selectinload(OfertaAyuda.items),
            selectinload(OfertaAyuda.organizacion),
            selectinload(OfertaAyuda.organizaciones),
        )

    def listar(
        self,
        db: Session,
        emergencia_id: Optional[int] = None,
        organizacion_id: Optional[int] = None,
    ) -> list[OfertaAyuda]:
        query = self._consulta_con_relaciones(db)
        if emergencia_id is not None:
            query = query.filter(OfertaAyuda.emergencia_id == emergencia_id)
        if organizacion_id is not None:
            # Una ONG ve tanto las ofertas que lidera como aquellas en las que
            # participa como socia de un consorcio.
            query = query.filter(
                or_(
                    OfertaAyuda.organizacion_id == organizacion_id,
                    OfertaAyuda.organizaciones.any(
                        Organizacion.id == organizacion_id
                    ),
                )
            )
        return query.order_by(OfertaAyuda.id.desc()).all()

    def listar_de_emergencia(
        self, db: Session, emergencia_id: int
    ) -> list[OfertaAyuda]:
        return (
            self._consulta_con_relaciones(db)
            .filter(OfertaAyuda.emergencia_id == emergencia_id)
            .order_by(OfertaAyuda.id.asc())
            .all()
        )

    def obtener_por_id(
        self, db: Session, oferta_id: int
    ) -> Optional[OfertaAyuda]:
        return (
            self._consulta_con_relaciones(db)
            .filter(OfertaAyuda.id == oferta_id)
            .scalar()
        )

    def crear(self, db: Session, oferta: OfertaAyuda) -> OfertaAyuda:
        db.add(oferta)
        db.commit()
        db.refresh(oferta)
        return oferta

    def reemplazar_items(
        self, db: Session, oferta: OfertaAyuda, items: list[OfertaItem]
    ) -> None:
        """Sustituye el detalle de la oferta por el indicado.

        El borrado se envia a la base antes del alta para no violar
        `uq_oferta_lote` cuando un lote sigue presente en la nueva version.
        """
        oferta.items.clear()
        db.flush()
        oferta.items = items

    def actualizar(self, db: Session, oferta: OfertaAyuda) -> OfertaAyuda:
        db.commit()
        db.refresh(oferta)
        return oferta
