from typing import Optional

from sqlalchemy.orm import Session

from ..models import RecursoInventario


class RecursoInventarioRepository:
    def obtener_por_id(
        self, db: Session, recurso_id: int
    ) -> Optional[RecursoInventario]:
        return db.get(RecursoInventario, recurso_id)

    def listar_de_organizacion(
        self, db: Session, organizacion_id: int
    ) -> list[RecursoInventario]:
        return (
            db.query(RecursoInventario)
            .filter(RecursoInventario.organizacion_id == organizacion_id)
            .order_by(RecursoInventario.id.asc())
            .all()
        )

    def crear(
        self, db: Session, recurso: RecursoInventario
    ) -> RecursoInventario:
        db.add(recurso)
        db.commit()
        db.refresh(recurso)
        return recurso

    def actualizar(
        self, db: Session, recurso: RecursoInventario
    ) -> RecursoInventario:
        db.commit()
        db.refresh(recurso)
        return recurso

    def eliminar(self, db: Session, recurso: RecursoInventario) -> None:
        db.delete(recurso)
        db.commit()
