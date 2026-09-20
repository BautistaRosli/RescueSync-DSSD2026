from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ..models import Emergencia, OfertaAyuda, OfertaItem, Organizacion
from ..schemas.oferta import OfertaAyudaCreate, OfertaAyudaUpdate


def _query(db: Session):
    return db.query(OfertaAyuda).options(
        selectinload(OfertaAyuda.items),
        selectinload(OfertaAyuda.organizacion),
    )


def _validar_items(db: Session, emergencia_id: int, items) -> list[OfertaItem]:
    emergencia = db.get(Emergencia, emergencia_id)
    if emergencia is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    lotes_validos = {lote.id for lote in emergencia.lotes}
    vistos = set()
    nuevos = []
    for item in items:
        if item.lote_necesidad_id not in lotes_validos:
            raise HTTPException(
                status_code=400,
                detail=f"El lote {item.lote_necesidad_id} no pertenece a la emergencia {emergencia_id}",
            )
        if item.lote_necesidad_id in vistos:
            raise HTTPException(
                status_code=400,
                detail=f"Lote duplicado en la oferta: {item.lote_necesidad_id}",
            )
        vistos.add(item.lote_necesidad_id)
        nuevos.append(OfertaItem(**item.model_dump()))
    return nuevos


def list_ofertas(
    db: Session,
    emergencia_id: Optional[int] = None,
    organizacion_id: Optional[int] = None,
) -> list[OfertaAyuda]:
    query = _query(db)
    if emergencia_id is not None:
        query = query.filter(OfertaAyuda.emergencia_id == emergencia_id)
    if organizacion_id is not None:
        query = query.filter(
            OfertaAyuda.organizacion_id == organizacion_id
        )
    return query.order_by(OfertaAyuda.id.desc()).all()


def get_oferta(db: Session, oferta_id: int) -> OfertaAyuda:
    oferta = (
        _query(db).filter(OfertaAyuda.id == oferta_id).scalar()
    )
    if oferta is None:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    return oferta


def create_oferta(db: Session, data: OfertaAyudaCreate) -> OfertaAyuda:
    if db.get(Organizacion, data.organizacion_id) is None:
        raise HTTPException(
            status_code=404, detail="Organización no encontrada"
        )
    items = _validar_items(db, data.emergencia_id, data.items)
    oferta = OfertaAyuda(
        emergencia_id=data.emergencia_id,
        organizacion_id=data.organizacion_id,
        observaciones=data.observaciones,
    )
    oferta.items = items
    db.add(oferta)
    db.commit()
    db.refresh(oferta)
    return oferta


def update_oferta(
    db: Session, oferta_id: int, data: OfertaAyudaUpdate
) -> OfertaAyuda:
    oferta = get_oferta(db, oferta_id)
    if data.observaciones is not None:
        oferta.observaciones = data.observaciones
    if data.items is not None:
        oferta.items = _validar_items(db, oferta.emergencia_id, data.items)
    db.commit()
    db.refresh(oferta)
    return oferta


def _serializar_listado(oferta: OfertaAyuda) -> dict:
    return {
        "id": oferta.id,
        "emergencia_id": oferta.emergencia_id,
        "organizacion_id": oferta.organizacion_id,
        "organizacion_nombre": (
            oferta.organizacion.nombre if oferta.organizacion else None
        ),
        "observaciones": oferta.observaciones,
        "fecha_hora_oferta": oferta.fecha_hora_oferta,
        "items": [
            {
                "id": item.id,
                "lote_necesidad_id": item.lote_necesidad_id,
                "cantidad_ofrecida": item.cantidad_ofrecida,
                "descripcion": item.descripcion,
            }
            for item in oferta.items
        ],
    }


def list_ofertas_emergencia(
    db: Session, emergencia_id: int
) -> list[dict]:
    if db.get(Emergencia, emergencia_id) is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    ofertas = (
        _query(db)
        .filter(OfertaAyuda.emergencia_id == emergencia_id)
        .order_by(OfertaAyuda.id.asc())
        .all()
    )
    return [_serializar_listado(oferta) for oferta in ofertas]


def list_consolidadas(db: Session, emergencia_id: int) -> dict:
    if db.get(Emergencia, emergencia_id) is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )
    ofertas = (
        _query(db)
        .filter(OfertaAyuda.emergencia_id == emergencia_id)
        .order_by(OfertaAyuda.id.asc())
        .all()
    )
    return {
        "emergencia_id": emergencia_id,
        "ofertas": [
            {
                "organizacion_id": oferta.organizacion_id,
                "organizacion_nombre": (
                    oferta.organizacion.nombre if oferta.organizacion else ""
                ),
                "items": [
                    {
                        "lote_id": item.lote_necesidad_id,
                        "cantidad_ofrecida": item.cantidad_ofrecida,
                        "descripcion": item.descripcion,
                    }
                    for item in oferta.items
                ],
            }
            for oferta in ofertas
        ],
    }