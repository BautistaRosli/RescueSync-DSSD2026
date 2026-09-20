from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ..models import Emergencia, Municipio
from ..schemas.emergencia import EmergenciaCreate, EmergenciaUpdate


def _query(db: Session):
    return db.query(Emergencia).options(selectinload(Emergencia.lotes))


def list_emergencias(
    db: Session,
    municipio_id: Optional[int] = None,
    publicada: Optional[bool] = None,
) -> list[Emergencia]:
    query = _query(db)
    if municipio_id is not None:
        query = query.filter(Emergencia.municipio_id == municipio_id)
    if publicada is not None:
        query = query.filter(Emergencia.publicada == publicada)
    return query.order_by(Emergencia.id.desc()).all()


def get_emergencia(db: Session, emergencia_id: int) -> Emergencia:
    emergencia = (
        _query(db).filter(Emergencia.id == emergencia_id).scalar()
    )
    if emergencia is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    return emergencia


def create_emergencia(db: Session, data: EmergenciaCreate) -> Emergencia:
    if db.get(Municipio, data.municipio_id) is None:
        raise HTTPException(status_code=404, detail="Municipio no encontrado")
    emergencia = Emergencia(**data.model_dump())
    db.add(emergencia)
    db.commit()
    db.refresh(emergencia)
    return emergencia


def update_emergencia(
    db: Session, emergencia_id: int, data: EmergenciaUpdate
) -> Emergencia:
    emergencia = get_emergencia(db, emergencia_id)
    updates = data.model_dump(exclude_unset=True)
    if "municipio_id" in updates:
        if updates["municipio_id"] is not None and db.get(
            Municipio, updates["municipio_id"]
        ) is None:
            raise HTTPException(
                status_code=404, detail="Municipio no encontrado"
            )
    for field, value in updates.items():
        setattr(emergencia, field, value)
    db.commit()
    db.refresh(emergencia)
    return emergencia


def publicar_emergencia(db: Session, emergencia_id: int) -> Emergencia:
    emergencia = get_emergencia(db, emergencia_id)
    if emergencia.publicada:
        raise HTTPException(
            status_code=409, detail="La emergencia ya fue publicada"
        )
    emergencia.publicada = True
    emergencia.fecha_publicacion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(emergencia)
    return emergencia