from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..dto import LoteNecesidadRespuesta
from ..integrations.bonita.client import BonitaClientError, bonita_client
from ..models import LoteNecesidad
from ..repositories import LoteNecesidadRepository
from ..schemas import LoteNecesidadActualizar, LoteNecesidadCrear
from .emergencias_service import EmergenciaService
from .ofertas_service import OfertaService


class LoteService:
    def __init__(self) -> None:
        self._repository = LoteNecesidadRepository()
        self._emergencias = EmergenciaService()
        self._ofertas = OfertaService()

    def listar_lotes(
        self, db: Session, emergencia_id: int
    ) -> list[LoteNecesidadRespuesta]:
        self._emergencias.obtener_emergencia_entidad(db, emergencia_id)
        lotes = self._repository.listar_de_emergencia(db, emergencia_id)
        return [LoteNecesidadRespuesta.model_validate(l) for l in lotes]

    def obtener_lote(
        self, db: Session, lote_id: int
    ) -> LoteNecesidadRespuesta:
        lote = self._obtener_lote_entidad(db, lote_id)
        return LoteNecesidadRespuesta.model_validate(lote)

    async def crear_lote(
        self, db: Session, emergencia_id: int, data: LoteNecesidadCrear
    ) -> LoteNecesidadRespuesta:
        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id
        )
        if emergencia.publicada:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La emergencia ya fue publicada: "
                    "sus lotes no se pueden modificar"
                ),
            )

        # Barrera de sincronizacion: el proceso Bonita "Generar lotes" solo
        # avanza cuando se crea un lote aca. Se libera ANTES de insertar para
        # que, si Bonita falla, el lote no quede creado.
        # La tarea debe asignarse a un usuario real del actor porque el usuario
        # tecnico no puede autoasignarse para ejecutarla por API.
        try:
            if emergencia.bonita_case_id:
                tarea = await bonita_client.obtener_tarea_pendiente(
                    int(emergencia.bonita_case_id), "Generar lotes"
                )
                if tarea is not None:
                    miembro = await bonita_client.obtener_miembro_actor(
                        int(tarea["actorId"])
                    )
                    if miembro is None:
                        raise HTTPException(
                            status_code=503,
                            detail=(
                                "No se pudo liberar la barrera en Bonita: "
                                "la tarea 'Generar lotes' no tiene "
                                "usuarios asignados a su actor"
                            ),
                        )
                    await bonita_client.asignar_tarea(
                        tarea["id"], int(miembro["user_id"])
                    )
                    await bonita_client.ejecutar_tarea(tarea["id"])
        except BonitaClientError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo liberar la barrera en Bonita: {exc}",
            )

        lote = LoteNecesidad(
            emergencia_id=emergencia_id, **data.model_dump()
        )
        creado = self._repository.crear(db, lote)
        return LoteNecesidadRespuesta.model_validate(creado)

    def actualizar_lote(
        self, db: Session, lote_id: int, data: LoteNecesidadActualizar
    ) -> LoteNecesidadRespuesta:
        lote = self._obtener_lote_entidad(db, lote_id)
        self._verificar_emergencia_no_publicada(db, lote.emergencia_id)
        lote = self._obtener_lote_entidad(db, lote_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(lote, field, value)
        actualizado = self._repository.actualizar(db, lote)
        return LoteNecesidadRespuesta.model_validate(actualizado)

    def eliminar_lote(self, db: Session, lote_id: int) -> None:
        lote = self._obtener_lote_entidad(db, lote_id)
        self._verificar_emergencia_no_publicada(db, lote.emergencia_id)
        lote = self._obtener_lote_entidad(db, lote_id)
        if self._ofertas.existe_referencia_a_lote(db, lote_id):
            raise HTTPException(
                status_code=409,
                detail="No se puede eliminar un lote con ofertas asociadas",
            )
        self._repository.eliminar(db, lote)

    def _verificar_emergencia_no_publicada(
        self, db: Session, emergencia_id: int
    ) -> None:
        """Congela la escritura de lotes cuando la emergencia ya fue publicada.

        El 404 de la emergencia padre lo sigue resolviendo el service de
        emergencias; aca solo se agrega el bloqueo por publicacion.
        """
        emergencia = self._emergencias.obtener_emergencia_entidad(
            db, emergencia_id, bloquear=True
        )
        if emergencia.publicada:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La emergencia ya fue publicada: "
                    "sus lotes no se pueden modificar"
                ),
            )

    def _obtener_lote_entidad(
        self, db: Session, lote_id: int
    ) -> LoteNecesidad:
        lote = self._repository.obtener_por_id(db, lote_id)
        if lote is None:
            raise HTTPException(status_code=404, detail="Lote no encontrado")
        return lote
