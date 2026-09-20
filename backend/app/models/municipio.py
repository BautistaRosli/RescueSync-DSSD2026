from __future__ import annotations

from typing import List, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Municipio(Base):
    """Municipio afectado que registra la emergencia."""

    __tablename__ = "municipios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    provincia: Mapped[Optional[str]] = mapped_column(String(100))
    localidad: Mapped[Optional[str]] = mapped_column(String(150))
    contacto: Mapped[Optional[str]] = mapped_column(String(150))

    emergencias: Mapped[List["Emergencia"]] = relationship(
        back_populates="municipio"
    )
    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="municipio")