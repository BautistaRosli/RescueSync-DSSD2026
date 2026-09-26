from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .rol import Rol


class Usuario(Base):
    """Usuario de la plataforma con rol (distinción de actores de la E2)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    rol_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id")
    )
    municipio_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("municipios.id")
    )
    organizacion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizaciones.id")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    rol: Mapped[Rol] = relationship(back_populates="usuarios")
    municipio: Mapped[Optional["Municipio"]] = relationship(
        back_populates="usuarios"
    )
    organizacion: Mapped[Optional["Organizacion"]] = relationship(
        back_populates="usuarios"
    )
