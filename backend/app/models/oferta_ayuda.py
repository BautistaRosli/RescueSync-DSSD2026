from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


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