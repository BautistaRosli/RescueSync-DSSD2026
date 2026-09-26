from typing import Optional

from sqlalchemy.orm import Session

from .models import LoteNecesidad


class LoteNecesidadRepository:
    def obtener_por_id(
        self, db: Session, lote_id: int
    ) -> Optional[LoteNecesidad]:
        return db.get(LoteNecesidad, lote_id)

    def listar_de_emergencia(
        self, db: Session, emergencia_id: int
    ) -> list[LoteNecesidad]:
        return (
            db.query(LoteNecesidad)
            .filter(LoteNecesidad.emergencia_id == emergencia_id)
            .order_by(LoteNecesidad.id.asc())
            .all()
        )

    def crear(
        self, db: Session, lote: LoteNecesidad
    ) -> LoteNecesidad:
        db.add(lote)
        db.commit()
        db.refresh(lote)
        return lote

    def actualizar(self, db: Session, lote: LoteNecesidad) -> LoteNecesidad:
        db.commit()
        db.refresh(lote)
        return lote

    def eliminar(self, db: Session, lote: LoteNecesidad) -> None:
        db.delete(lote)
        db.commit()
