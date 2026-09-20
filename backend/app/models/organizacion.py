from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Organizacion(Base):
    """ONG / organismo que carga Ofertas de Ayuda."""

    __tablename__ = "organizaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), default="ong")
    email: Mapped[Optional[str]] = mapped_column(String(150))
    telefono: Mapped[Optional[str]] = mapped_column(String(50))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    ofertas: Mapped[List["OfertaAyuda"]] = relationship(
        back_populates="organizacion"
    )
    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="organizacion")