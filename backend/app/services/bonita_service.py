import json
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ..integrations.bonita_client import BonitaClientError, bonita_client
from ..models import Emergencia

logger = logging.getLogger(__name__)


async def iniciar_emergencia(db: Session, emergencia_id: int) -> int:
    
    # Obtener la emergencia de la base de datos
    emergencia = (
        db.query(Emergencia)
        .options(selectinload(Emergencia.lotes))
        .filter(Emergencia.id == emergencia_id)
        .scalar()
    )
    if emergencia is None:
        raise HTTPException(status_code=404, detail="Emergencia no encontrada")

    # Idempotencia: si ya tiene caso, no crear otro
    if emergencia.bonita_case_id:
        return int(emergencia.bonita_case_id)

    # Validar que tenga lotes
    if not emergencia.lotes:
        raise HTTPException(
            status_code=400,
            detail="La emergencia no tiene lotes de necesidad cargados",
        )

    # Armar variables (simples, con lotes serializados como JSON string)
    variables = {
        "emergencia_id": emergencia.id,
        "nivel_gravedad": emergencia.nivel_gravedad,
        "zona_afectada": emergencia.zona_afectada,
        "descripcion_inicial": emergencia.descripcion_inicial,
        "lotes_json": json.dumps(
            [
                {
                    "tipo": lote.tipo,
                    "cantidad": lote.cantidad,
                    "unidad": lote.unidad,
                    "descripcion": lote.descripcion,
                }
                for lote in emergencia.lotes
            ],
            default=str,
        ),
    }

    logger.info(f"Variables a enviar a Bonita: {variables}")

    try:
        case_id = await bonita_client.start_emergency_process(variables)
    except BonitaClientError as exc:
        logger.error(f"Error iniciando caso en Bonita: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo iniciar el proceso en Bonita: {exc}",
        )

    emergencia.bonita_case_id = str(case_id)
    emergencia.bonita_variables_json = json.dumps(variables, default=str)
    db.commit()
    db.refresh(emergencia)

    return case_id