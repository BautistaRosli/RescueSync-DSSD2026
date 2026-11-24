"""Referencias nacionales y distribución declarada, sin alterar tablas previas."""

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class OrganizacionCloud(Base):
    __tablename__ = "organizaciones_cloud"
    __table_args__ = (CheckConstraint("ong_id > 0"),)

    organizacion_id: Mapped[int] = mapped_column(
        ForeignKey("organizaciones.id", ondelete="CASCADE"), primary_key=True
    )
    ong_id: Mapped[int] = mapped_column(nullable=False)


class LoteRecursoCloud(Base):
    __tablename__ = "lotes_recursos_cloud"
    __table_args__ = (CheckConstraint("tipo_recurso_id > 0"),)

    lote_id: Mapped[int] = mapped_column(
        ForeignKey("lotes_necesidad.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_recurso_id: Mapped[int] = mapped_column(nullable=False)


class AporteOfertaItem(Base):
    __tablename__ = "aportes_oferta_items"
    __table_args__ = (CheckConstraint("cantidad > 0"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("oferta_items.id", ondelete="CASCADE"), primary_key=True
    )
    organizacion_id: Mapped[int] = mapped_column(
        ForeignKey("organizaciones.id"), primary_key=True
    )
    cantidad: Mapped[int] = mapped_column(nullable=False)
