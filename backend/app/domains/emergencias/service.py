import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...integrations.bonita.client import BonitaClientError, bonita_client
from .models import Emergencia
from .repository import EmergenciaRepository
from .schemas import (
    EmergenciaActualizar,
    EmergenciaCrear,
)

logger = logging.getLogger(__name__)


class EmergenciaService:
    def __init__(self) -> None:
        self._repository = EmergenciaRepository()

    def listar_emergencias(
        self,
        db: Session,
        publicada: Optional[bool] = None,
    ):
        return self._repository.listar(
            db, publicada=publicada
        )

    def obtener_emergencia(self, db: Session, emergencia_id: int) -> Emergencia:
        emergencia = self._repository.obtener_por_id(db, emergencia_id)
        if emergencia is None:
            raise HTTPException(
                status_code=404, detail="Emergencia no encontrada"
            )
        return emergencia

    def crear_emergencia(
        self, db: Session, data: EmergenciaCrear
    ) -> Emergencia:
        emergencia = Emergencia(**data.model_dump())
        return self._repository.crear(db, emergencia)

    def actualizar_emergencia(
        self, db: Session, emergencia_id: int, data: EmergenciaActualizar
    ) -> Emergencia:
        emergencia = self.obtener_emergencia(db, emergencia_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(emergencia, field, value)
        return self._repository.actualizar(db, emergencia)

    def publicar_emergencia(
        self, db: Session, emergencia_id: int
    ) -> Emergencia:
        """Marca la emergencia como publicada.

        No interactua con Bonita: la publicacion es un acto administrativo.
        """
        emergencia = self.obtener_emergencia(db, emergencia_id)
        if emergencia.publicada:
            raise HTTPException(
                status_code=409, detail="La emergencia ya fue publicada"
            )
        emergencia.publicada = True
        emergencia.fecha_publicacion = datetime.now(timezone.utc)
        return self._repository.actualizar(db, emergencia)

    async def iniciar_proceso_bonita(
        self, db: Session, emergencia_id: int
    ) -> int:
        """Instancia en Bonita el proceso de convocatoria de la emergencia.

        Es idempotente: si la emergencia ya tiene un caso, devuelve el mismo.
        """
        emergencia = self.obtener_emergencia(db, emergencia_id)

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
        self._repository.actualizar(db, emergencia)

        return case_id
