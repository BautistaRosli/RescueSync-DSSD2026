from __future__ import annotations

from typing import List

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Rol(Base):
    """Rol de usuario almacenado como dato en la tabla roles."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )

    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol")
