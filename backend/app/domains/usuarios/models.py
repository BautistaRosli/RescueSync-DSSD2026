from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...database import Base


class RolUsuario:
    OPERADOR_MUNICIPAL = "OPERADOR_MUNICIPAL"
    CENTRO_COORDINADOR = "CENTRO_COORDINADOR"
    REPRESENTANTE_ONG = "REPRESENTANTE_ONG"


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


class Usuario(Base):
    """Usuario de la plataforma con rol (distinción de actores de la E2)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(
        String(30), default=RolUsuario.OPERADOR_MUNICIPAL, nullable=False
    )
    municipio_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("municipios.id")
    )
    organizacion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizaciones.id")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    municipio: Mapped[Optional["Municipio"]] = relationship(
        back_populates="usuarios"
    )
    organizacion: Mapped[Optional["Organizacion"]] = relationship(
        back_populates="usuarios"
    )
