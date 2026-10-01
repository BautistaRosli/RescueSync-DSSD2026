from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..dto import RecursoInventarioRespuesta
from ..models import RecursoInventario
from ..repositories import RecursoInventarioRepository
from ..schemas import RecursoInventarioActualizar, RecursoInventarioCrear
from .usuarios_service import OrganizacionService


class InventarioService:
    def __init__(self) -> None:
        self._repository = RecursoInventarioRepository()
        self._organizaciones = OrganizacionService()

    def listar_recursos(
        self, db: Session, organizacion_id: int
    ) -> list[RecursoInventarioRespuesta]:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recursos = self._repository.listar_de_organizacion(db, organizacion_id)
        return [
            RecursoInventarioRespuesta.model_validate(r) for r in recursos
        ]

    def crear_recurso(
        self,
        db: Session,
        organizacion_id: int,
        data: RecursoInventarioCrear,
    ) -> RecursoInventarioRespuesta:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recurso = RecursoInventario(
            organizacion_id=organizacion_id, **data.model_dump()
        )
        creado = self._repository.crear(db, recurso)
        return RecursoInventarioRespuesta.model_validate(creado)

    def actualizar_recurso(
        self,
        db: Session,
        organizacion_id: int,
        recurso_id: int,
        data: RecursoInventarioActualizar,
    ) -> RecursoInventarioRespuesta:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recurso = self._obtener_recurso_entidad(
            db, recurso_id, organizacion_id
        )
        for field, value in data.model_dump().items():
            setattr(recurso, field, value)
        actualizado = self._repository.actualizar(db, recurso)
        return RecursoInventarioRespuesta.model_validate(actualizado)

    def eliminar_recurso(
        self, db: Session, organizacion_id: int, recurso_id: int
    ) -> None:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recurso = self._obtener_recurso_entidad(
            db, recurso_id, organizacion_id
        )
        self._repository.eliminar(db, recurso)

    def _obtener_recurso_entidad(
        self, db: Session, recurso_id: int, organizacion_id: int
    ) -> RecursoInventario:
        """Resuelve el recurso validando que pertenezca a la organizacion.

        El chequeo de pertenencia evita editar o borrar el recurso de otra
        ONG entrando por la ruta equivocada: si el id existe pero cuelga de
        otra organizacion, para esta ruta el recurso no existe.
        """
        recurso = self._repository.obtener_por_id(db, recurso_id)
        if recurso is None or recurso.organizacion_id != organizacion_id:
            raise HTTPException(
                status_code=404, detail="Recurso no encontrado"
            )
        return recurso
