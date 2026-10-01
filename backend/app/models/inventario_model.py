from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RecursoInventario(Base):
    """Recurso disponible en el inventario propio de una ONG."""

    __tablename__ = "recursos_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sin relationship hacia Organizacion: nadie navega organizacion.recursos
    # y agregarlo obligaria a tocar usuarios_model.py. La FK sola alcanza.
    organizacion_id: Mapped[int] = mapped_column(
        ForeignKey("organizaciones.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    cantidad_total: Mapped[int] = mapped_column(Integer, nullable=False)
    unidad: Mapped[Optional[str]] = mapped_column(String(50))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
