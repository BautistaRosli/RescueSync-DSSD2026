from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...database import Base


class NivelGravedad:
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


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


class Emergencia(Base):
    """Emergencia registrada por un municipio afectado."""

    __tablename__ = "emergencias"

    id: Mapped[int] = mapped_column(primary_key=True)
    municipio_id: Mapped[int] = mapped_column(
        ForeignKey("municipios.id"), nullable=False
    )
    nivel_gravedad: Mapped[str] = mapped_column(
        String(20), default=NivelGravedad.MEDIA, nullable=False
    )
    zona_afectada: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion_inicial: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_hora_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    publicada: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    fecha_publicacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    bonita_case_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    tipo_desastre: Mapped[Optional[str]] = mapped_column(String(100))
    bonita_variables_json: Mapped[Optional[str]] = mapped_column(Text)

    municipio: Mapped["Municipio"] = relationship(back_populates="emergencias")
    lotes: Mapped[List["LoteNecesidad"]] = relationship(
        back_populates="emergencia", cascade="all, delete-orphan"
    )
    ofertas: Mapped[List["OfertaAyuda"]] = relationship(
        back_populates="emergencia", cascade="all, delete-orphan"
    )
