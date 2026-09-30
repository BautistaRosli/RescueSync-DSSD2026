import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..dto import EmergenciaRespuesta, EmergenciasPaginadas
from ..integrations.bonita.client import BonitaClientError, bonita_client
from ..integrations.email.service import notificar_nueva_emergencia
from ..models import EstadoEmergencia, Emergencia
from ..repositories import EmergenciaRepository, UsuarioRepository
from ..schemas import (
    EmergenciaActualizar,
    EmergenciaCrear,
)

logger = logging.getLogger(__name__)

NOMBRE_ROL_CENTRO_COORDINADOR = "CENTRO_COORDINADOR"


class EmergenciaService:
    def __init__(self) -> None:
        self._repository = EmergenciaRepository()
        self._usuarios = UsuarioRepository()

    def listar_emergencias(
        self,
        db: Session,
        publicada: Optional[bool] = None,
    ) -> list[EmergenciaRespuesta]:
        emergencias = self._repository.listar(db, publicada=publicada)
        return [EmergenciaRespuesta.model_validate(e) for e in emergencias]

    def listar_emergencias_paginadas(
        self,
        db: Session,
        publicada: bool,
        pagina: int = 1,
        por_pagina: int = 10,
    ) -> EmergenciasPaginadas:
        """Bandeja paginada: bucket de no publicadas o de publicadas."""
        total = self._repository.contar_por_publicada(db, publicada)
        emergencias = self._repository.listar_paginado(
            db, publicada, pagina, por_pagina
        )
        return EmergenciasPaginadas(
            items=[EmergenciaRespuesta.model_validate(e) for e in emergencias],
            pagina=pagina,
            por_pagina=por_pagina,
            total=total,
            paginas=math.ceil(total / por_pagina) if total else 0,
        )

    def obtener_emergencia_entidad(
        self, db: Session, emergencia_id: int, bloquear: bool = False
    ) -> Emergencia:
        """Devuelve la entidad para uso de otros services."""
        return self._obtener_emergencia_entidad(db, emergencia_id, bloquear)

    def obtener_emergencia(
        self, db: Session, emergencia_id: int
    ) -> EmergenciaRespuesta:
        emergencia = self._obtener_emergencia_entidad(db, emergencia_id)
        return EmergenciaRespuesta.model_validate(emergencia)

    def crear_emergencia(
        self,
        db: Session,
        data: EmergenciaCrear,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> EmergenciaRespuesta:
        emergencia = Emergencia(**data.model_dump())
        creada = self._repository.crear(db, emergencia)
        respuesta = EmergenciaRespuesta.model_validate(creada)
        if background_tasks is not None:
            self._programar_notificacion(db, creada, background_tasks)
        return respuesta

    def _programar_notificacion(
        self,
        db: Session,
        emergencia: Emergencia,
        background_tasks: BackgroundTasks,
    ) -> None:
        """Agenda el aviso por email al Centro Coordinador.

        Los destinatarios y los datos de la emergencia se resuelven aca, con
        la sesion de la request todavia abierta. La background task recibe
        solo primitivos porque su sesion ya fue cerrada.
        """
        destinatarios = [
            usuario.email
            for usuario in self._usuarios.listar_por_rol_nombre(
                db, NOMBRE_ROL_CENTRO_COORDINADOR
            )
        ]
        background_tasks.add_task(
            notificar_nueva_emergencia,
            destinatarios,
            emergencia.id,
            emergencia.nivel_gravedad,
            emergencia.zona_afectada,
            emergencia.descripcion_inicial,
            emergencia.fecha_hora_registro,
        )

    def actualizar_emergencia(
        self, db: Session, emergencia_id: int, data: EmergenciaActualizar
    ) -> EmergenciaRespuesta:
        emergencia = self._obtener_emergencia_entidad(db, emergencia_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(emergencia, field, value)
        actualizada = self._repository.actualizar(db, emergencia)
        return EmergenciaRespuesta.model_validate(actualizada)

    def publicar_emergencia(
        self, db: Session, emergencia_id: int
    ) -> EmergenciaRespuesta:
        """Publica la emergencia y abre la convocatoria de ofertas.

        No interactua con Bonita: la publicacion es un acto administrativo.
        """
        emergencia = self._obtener_emergencia_entidad(db, emergencia_id, bloquear=True)
        if emergencia.publicada:
            raise HTTPException(
                status_code=409, detail="La emergencia ya fue publicada"
            )
        if not emergencia.lotes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "La emergencia no tiene lotes de necesidad cargados: "
                    "no se puede publicar"
                ),
            )
        emergencia.publicada = True
        emergencia.fecha_publicacion = datetime.now(timezone.utc)
        emergencia.estado = EstadoEmergencia.ESPERA_OFERTAS
        publicada = self._repository.actualizar(db, emergencia)
        return EmergenciaRespuesta.model_validate(publicada)

    async def iniciar_proceso_bonita(
        self, db: Session, emergencia_id: int
    ) -> int:
        """Instancia en Bonita el proceso de convocatoria de la emergencia.

        Es idempotente: si la emergencia ya tiene un caso, devuelve el mismo.
        """
        # La espera del bloqueo no debe impedir que otra petición termine su HTTP.
        emergencia = await run_in_threadpool(
            self._obtener_emergencia_entidad, db, emergencia_id, bloquear=True
        )

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

    def _obtener_emergencia_entidad(
        self, db: Session, emergencia_id: int, bloquear: bool = False
    ) -> Emergencia:
        emergencia = self._repository.obtener_por_id(db, emergencia_id, bloquear)
        if emergencia is None:
            raise HTTPException(
                status_code=404, detail="Emergencia no encontrada"
            )
        return emergencia
