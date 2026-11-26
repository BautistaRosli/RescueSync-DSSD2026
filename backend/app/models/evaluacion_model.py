"""Referencias nacionales y distribución declarada, sin alterar tablas previas."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
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


class EvaluacionCloud(Base):
    """Ronda municipal y respuesta íntegra; las rondas anteriores se conservan."""

    __tablename__ = "evaluaciones_cloud"

    id: Mapped[int] = mapped_column(primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencias.id", ondelete="CASCADE"), index=True
    )
    solicitud_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    caso_id: Mapped[str] = mapped_column(String(50), nullable=False)
    solicitud_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluacion_json: Mapped[str | None] = mapped_column(Text)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RegistroRecursos(Base):
    """Intención durable: un envío incierto nunca habilita otro bloqueo."""

    __tablename__ = "registros_recursos"
    __table_args__ = (CheckConstraint("estado IN ('ENVIADO', 'RECHAZADO', 'CONFIRMADO')"),)

    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencias.id", ondelete="CASCADE"), primary_key=True
    )
    caso_id: Mapped[str] = mapped_column(String(50), nullable=False)
    seleccion_json: Mapped[str] = mapped_column(Text, nullable=False)
    solicitud_json: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    respuesta_json: Mapped[str | None] = mapped_column(Text)
