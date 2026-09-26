from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .models import Emergencia


class EmergenciaRepository:
    def _consulta_con_lotes(self, db: Session):
        return db.query(Emergencia).options(selectinload(Emergencia.lotes))

    def listar(
        self,
        db: Session,
        publicada: Optional[bool] = None,
    ) -> list[Emergencia]:
        query = self._consulta_con_lotes(db)
        if publicada is not None:
            query = query.filter(Emergencia.publicada == publicada)
        return query.order_by(Emergencia.id.desc()).all()

    def obtener_por_id(
        self, db: Session, emergencia_id: int
    ) -> Optional[Emergencia]:
        return (
            self._consulta_con_lotes(db)
            .filter(Emergencia.id == emergencia_id)
            .scalar()
        )

    def crear(self, db: Session, emergencia: Emergencia) -> Emergencia:
        db.add(emergencia)
        db.commit()
        db.refresh(emergencia)
        return emergencia

    def actualizar(self, db: Session, emergencia: Emergencia) -> Emergencia:
        db.commit()
        db.refresh(emergencia)
        return emergencia
