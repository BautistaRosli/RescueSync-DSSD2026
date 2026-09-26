from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .models import Emergencia, Municipio


class MunicipioRepository:
    def obtener_por_id(self, db: Session, municipio_id: int) -> Optional[Municipio]:
        return db.get(Municipio, municipio_id)

    def listar(self, db: Session) -> list[Municipio]:
        return db.query(Municipio).order_by(Municipio.id.asc()).all()

    def crear(self, db: Session, municipio: Municipio) -> Municipio:
        db.add(municipio)
        db.commit()
        db.refresh(municipio)
        return municipio

    def actualizar(self, db: Session, municipio: Municipio) -> Municipio:
        db.commit()
        db.refresh(municipio)
        return municipio


class EmergenciaRepository:
    def _consulta_con_lotes(self, db: Session):
        return db.query(Emergencia).options(selectinload(Emergencia.lotes))

    def listar(
        self,
        db: Session,
        municipio_id: Optional[int] = None,
        publicada: Optional[bool] = None,
    ) -> list[Emergencia]:
        query = self._consulta_con_lotes(db)
        if municipio_id is not None:
            query = query.filter(Emergencia.municipio_id == municipio_id)
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
