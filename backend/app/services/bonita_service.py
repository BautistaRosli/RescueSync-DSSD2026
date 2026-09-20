import json

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ..integrations.bonita_client import BonitaClientError, bonita_client
from ..models import Emergencia


async def iniciar_emergencia(db: Session, emergencia_id: int) -> dict:
    emergencia = (
        db.query(Emergencia)
        .options(selectinload(Emergencia.lotes))
        .filter(Emergencia.id == emergencia_id)
        .scalar()
    )
    if emergencia is None:
        raise HTTPException(
            status_code=404, detail="Emergencia no encontrada"
        )

    variables = {
        "emergencia_id": str(emergencia.id),
        "nivel_gravedad": emergencia.nivel_gravedad,
        "zona_afectada": emergencia.zona_afectada,
        "descripcion_inicial": emergencia.descripcion_inicial,
        "lotes": [
            {
                "tipo": lote.tipo,
                "cantidad": lote.cantidad,
                "unidad": lote.unidad,
                "descripcion": lote.descripcion,
            }
            for lote in emergencia.lotes
        ],
    }

    try:
        case_id = await bonita_client.start_emergency_process(variables)
    except BonitaClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo iniciar el proceso en Bonita: {exc}",
        )

    emergencia.bonita_case_id = str(case_id)
    emergencia.bonita_variables_json = json.dumps(variables, default=str)
    db.commit()
    db.refresh(emergencia)
    return {"bonita_case_id": case_id}