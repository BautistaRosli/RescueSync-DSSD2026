from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...database import Base


class OfertaAyuda(Base):
    """Cabecera de una Oferta de Ayuda cargada por una ONG."""

    __tablename__ = "ofertas_ayuda"

    id: Mapped[int] = mapped_column(primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencias.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    organizacion_id: Mapped[int] = mapped_column(
        ForeignKey("organizaciones.id"), nullable=False
    )
    fecha_hora_oferta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    emergencia: Mapped["Emergencia"] = relationship(back_populates="ofertas")
    organizacion: Mapped["Organizacion"] = relationship(
        back_populates="ofertas"
    )
    items: Mapped[List["OfertaItem"]] = relationship(
        back_populates="oferta", cascade="all, delete-orphan"
    )


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
