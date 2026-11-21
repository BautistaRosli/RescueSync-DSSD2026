from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class LoteNecesidad(Base):
    """Lote de Necesidades: recurso y cantidad requerida de una emergencia."""

    __tablename__ = "lotes_necesidad"

    id: Mapped[int] = mapped_column(primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencias.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    unidad: Mapped[Optional[str]] = mapped_column(String(50))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    referencia_cloud: Mapped[Optional["LoteRecursoCloud"]] = relationship(
        cascade="all, delete-orphan", single_parent=True, lazy="selectin"
    )

    emergencia: Mapped["Emergencia"] = relationship(back_populates="lotes")
    items: Mapped[List["OfertaItem"]] = relationship(
        back_populates="lote_necesidad"
    )

    @property
    def tipo_recurso_id(self) -> Optional[int]:
        """Expone la equivalencia nacional sin duplicar su persistencia."""
        return self.referencia_cloud.tipo_recurso_id if self.referencia_cloud else None
