from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..emergencias.service import EmergenciaService
from ..ofertas.service import OfertaService
from .models import LoteNecesidad
from .repository import LoteNecesidadRepository
from .schemas import LoteNecesidadActualizar, LoteNecesidadCrear


class LoteService:
    def __init__(self) -> None:
        self._repository = LoteNecesidadRepository()
        self._emergencias = EmergenciaService()
        self._ofertas = OfertaService()

    def listar_lotes(
        self, db: Session, emergencia_id: int
    ) -> list[LoteNecesidad]:
        self._emergencias.obtener_emergencia(db, emergencia_id)
        return self._repository.listar_de_emergencia(db, emergencia_id)

    def obtener_lote(self, db: Session, lote_id: int) -> LoteNecesidad:
        lote = self._repository.obtener_por_id(db, lote_id)
        if lote is None:
            raise HTTPException(status_code=404, detail="Lote no encontrado")
        return lote

    def crear_lote(
        self, db: Session, emergencia_id: int, data: LoteNecesidadCrear
    ) -> LoteNecesidad:
        self._emergencias.obtener_emergencia(db, emergencia_id)
        lote = LoteNecesidad(
            emergencia_id=emergencia_id, **data.model_dump()
        )
        return self._repository.crear(db, lote)

    def actualizar_lote(
        self, db: Session, lote_id: int, data: LoteNecesidadActualizar
    ) -> LoteNecesidad:
        lote = self.obtener_lote(db, lote_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(lote, field, value)
        return self._repository.actualizar(db, lote)

    def eliminar_lote(self, db: Session, lote_id: int) -> None:
        lote = self.obtener_lote(db, lote_id)
        if self._ofertas.existe_referencia_a_lote(db, lote_id):
            raise HTTPException(
                status_code=409,
                detail="No se puede eliminar un lote con ofertas asociadas",
            )
        self._repository.eliminar(db, lote)
