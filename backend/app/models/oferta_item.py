from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class OfertaItem(Base):
    """Detalle de lo ofertado por lote de una Oferta de Ayuda."""

    __tablename__ = "oferta_items"
    __table_args__ = (
        UniqueConstraint("oferta_id", "lote_necesidad_id", name="uq_oferta_lote"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    oferta_id: Mapped[int] = mapped_column(
        ForeignKey("ofertas_ayuda.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lote_necesidad_id: Mapped[int] = mapped_column(
        ForeignKey("lotes_necesidad.id"), nullable=False
    )
    cantidad_ofrecida: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)

    oferta: Mapped["OfertaAyuda"] = relationship(back_populates="items")
    lote_necesidad: Mapped["LoteNecesidad"] = relationship(
        back_populates="items"
    )