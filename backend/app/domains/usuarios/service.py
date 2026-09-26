from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Organizacion
from .repository import OrganizacionRepository
from .schemas import OrganizacionActualizar, OrganizacionCrear


class OrganizacionService:
    def __init__(self) -> None:
        self._repository = OrganizacionRepository()

    def listar_organizaciones(self, db: Session) -> list[Organizacion]:
        return self._repository.listar(db)

    def obtener_organizacion(
        self, db: Session, organizacion_id: int
    ) -> Organizacion:
        organizacion = self._repository.obtener_por_id(db, organizacion_id)
        if organizacion is None:
            raise HTTPException(
                status_code=404, detail="Organización no encontrada"
            )
        return organizacion

    def crear_organizacion(
        self, db: Session, data: OrganizacionCrear
    ) -> Organizacion:
        return self._repository.crear(db, Organizacion(**data.model_dump()))

    def actualizar_organizacion(
        self, db: Session, organizacion_id: int, data: OrganizacionActualizar
    ) -> Organizacion:
        organizacion = self.obtener_organizacion(db, organizacion_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(organizacion, field, value)
        return self._repository.actualizar(db, organizacion)
