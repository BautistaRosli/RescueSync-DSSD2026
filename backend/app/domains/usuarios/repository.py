from typing import Optional

from sqlalchemy.orm import Session

from .models import Organizacion


class OrganizacionRepository:
    def obtener_por_id(
        self, db: Session, organizacion_id: int
    ) -> Optional[Organizacion]:
        return db.get(Organizacion, organizacion_id)

    def listar(self, db: Session) -> list[Organizacion]:
        return db.query(Organizacion).order_by(Organizacion.id.asc()).all()

    def crear(self, db: Session, organizacion: Organizacion) -> Organizacion:
        db.add(organizacion)
        db.commit()
        db.refresh(organizacion)
        return organizacion

    def actualizar(
        self, db: Session, organizacion: Organizacion
    ) -> Organizacion:
        db.commit()
        db.refresh(organizacion)
        return organizacion
