from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Emergencia, LoteNecesidad, OfertaItem
from ..schemas.lote import LoteNecesidadCreate, LoteNecesidadUpdate


def list_lotes(db: Session, emergencia_id: int) -> list[LoteNecesidad]:
    if db.get(Emergencia, emergencia_id) is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    return (
        db.query(LoteNecesidad)
        .filter(LoteNecesidad.emergencia_id == emergencia_id)
        .order_by(LoteNecesidad.id.asc())
        .all()
    )


def get_lote(db: Session, lote_id: int) -> LoteNecesidad:
    lote = db.get(LoteNecesidad, lote_id)
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return lote


def create_lote(
    db: Session, emergencia_id: int, data: LoteNecesidadCreate
) -> LoteNecesidad:
    if db.get(Emergencia, emergencia_id) is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    lote = LoteNecesidad(emergencia_id=emergencia_id, **data.model_dump())
    db.add(lote)
    db.commit()
    db.refresh(lote)
    return lote


def update_lote(
    db: Session, lote_id: int, data: LoteNecesidadUpdate
) -> LoteNecesidad:
    lote = get_lote(db, lote_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lote, field, value)
    db.commit()
    db.refresh(lote)
    return lote


def delete_lote(db: Session, lote_id: int) -> None:
    lote = get_lote(db, lote_id)
    referenciado = (
        db.query(OfertaItem.id)
        .filter(OfertaItem.lote_necesidad_id == lote_id)
        .first()
    )
    if referenciado is not None:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar un lote con ofertas asociadas",
        )
    db.delete(lote)
    db.commit()