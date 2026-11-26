import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, selectinload

from ..dto import (
    EmergenciaRespuesta,
    EmergenciasDashboard,
    EmergenciasPaginadas,
    DemandaOfertaRecurso,
    EmergenciasPorEstadoGravedad,
    EvolucionEmergencias,
    ParticipacionConsorcios,
    RankingONG,
    RecursoAdjudicadoPorMes,
)
from ..integrations.bonita.client import BonitaClientError, bonita_client
from ..integrations.email.service import notificar_nueva_emergencia
from ..integrations.prioridad.client import (
    PrioridadClientError,
    prioridad_client,
)
from ..models import (
    EstadoEmergencia,
    Emergencia,
    LoteNecesidad,
    OfertaAyuda,
    OfertaItem,
)
from ..repositories import EmergenciaRepository, UsuarioRepository
from ..schemas import (
    EmergenciaActualizar,
    EmergenciaCrear,
)
from ..schemas.emergencias_schema import EtapaBonita, SincronizacionCierresRespuesta

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

    def _leer_candidatos_cierre(self, db: Session) -> list[tuple[int, str]]:
        try:
            return self._repository.listar_candidatos_cierre(db)
        finally:
            # No mantener una transacción municipal durante la consulta remota.
            db.rollback()

    async def sincronizar_cierres(self, db: Session) -> SincronizacionCierresRespuesta:
        candidatos = await run_in_threadpool(self._leer_candidatos_cierre, db)
        if not candidatos:
            return SincronizacionCierresRespuesta(emergencias_resueltas=[])
        try:
            completados = await bonita_client.obtener_casos_completados({caso for _, caso in candidatos})
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo actualizar el estado de las emergencias. Intente nuevamente.") from None
        resueltas = await run_in_threadpool(
            self._repository.resolver_candidatos_cierre, db, candidatos, completados,
        )
        return SincronizacionCierresRespuesta(emergencias_resueltas=resueltas)

    def listar_emergencias_paginadas(
        self,
        db: Session,
        publicada: bool,
        estado: Optional[str] = None,
        pagina: int = 1,
        por_pagina: int = 10,
        casos_bonita: set[str] | None = None,
    ) -> EmergenciasPaginadas:
        """Bandeja paginada: bucket de no publicadas o de publicadas."""
        filtros = {"estado": estado}
        if casos_bonita is not None:
            filtros["casos_bonita"] = casos_bonita
        total = self._repository.contar_por_publicada(db, publicada, **filtros)
        emergencias = self._repository.listar_paginado(db, publicada, pagina, por_pagina, **filtros)
        return EmergenciasPaginadas(
            items=[EmergenciaRespuesta.model_validate(e) for e in emergencias],
            pagina=pagina,
            por_pagina=por_pagina,
            total=total,
            paginas=math.ceil(total / por_pagina) if total else 0,
        )

    async def listar_bandeja_por_etapa(
        self, db: Session, etapa: EtapaBonita, pagina: int, por_pagina: int,
    ) -> EmergenciasPaginadas:
        """Bonita determina la etapa; SQL filtra antes de contar y paginar."""
        estado = (EstadoEmergencia.ESPERA_OFERTAS if etapa == "esperando_ofertas"
                  else EstadoEmergencia.ESPERANDO_ADJUDICACION)
        try:
            if etapa == "esperando_ofertas":
                candidatos = await run_in_threadpool(self._repository.listar_casos_por_estado, db, estado)
                casos = await bonita_client.obtener_casos_con_ofertas_abiertas(candidatos)
            else:
                evaluando = await bonita_client.obtener_casos_con_tarea_lista("Evaluar proyecto")
                if etapa == "esperando_evaluacion":
                    casos = evaluando
                else:
                    seleccionando = await bonita_client.obtener_casos_con_tarea_lista("Seleccionar oferta")
                    # Una lectura durante la transición no adelanta la selección.
                    casos = seleccionando - evaluando
        except (BonitaClientError, httpx.RequestError):
            raise HTTPException(503, "No se pudo consultar la etapa de las emergencias en Bonita") from None
        return await run_in_threadpool(
            self.listar_emergencias_paginadas, db, True, estado, pagina, por_pagina,
            casos_bonita=casos,
        )

    def obtener_dashboard(
        self,
        db: Session,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        nivel_gravedad: Optional[str] = None,
    ) -> EmergenciasDashboard:
        emergencias = self._repository.listar(db)
        def fecha_normalizada(fecha: datetime) -> datetime:
            if fecha.tzinfo is None:
                return fecha
            return fecha.astimezone(timezone.utc).replace(tzinfo=None)

        desde_normalizado = fecha_normalizada(desde) if desde is not None else None
        hasta_normalizado = fecha_normalizada(hasta) if hasta is not None else None
        if desde is not None:
            emergencias = [
                emergencia for emergencia in emergencias
                if fecha_normalizada(emergencia.fecha_hora_registro) >= desde_normalizado
            ]
        if hasta is not None:
            emergencias = [
                emergencia for emergencia in emergencias
                if fecha_normalizada(emergencia.fecha_hora_registro) <= hasta_normalizado
            ]
        if nivel_gravedad is not None:
            emergencias = [
                emergencia for emergencia in emergencias
                if emergencia.nivel_gravedad == nivel_gravedad
            ]
        conteos_por_estado: dict[str, int] = {}
        evolucion_por_fecha: dict[str, dict[str, int]] = {}
        ahora = datetime.now(timezone.utc)
        tiempo_total_horas = 0.0
        cantidad_total_necesidades = 0
        emergencias_resueltas = 0
        emergencias_por_estado_y_gravedad: dict[tuple[str, str], int] = {}
        for emergencia in emergencias:
            if emergencia.estado is not None:
                conteos_por_estado[emergencia.estado] = (
                    conteos_por_estado.get(emergencia.estado, 0) + 1
                )
                clave_gravedad = (emergencia.estado, emergencia.nivel_gravedad)
                emergencias_por_estado_y_gravedad[clave_gravedad] = (
                    emergencias_por_estado_y_gravedad.get(clave_gravedad, 0) + 1
                )
            if emergencia.estado == EstadoEmergencia.RESUELTA:
                emergencias_resueltas += 1
            fecha = emergencia.fecha_hora_registro.date().isoformat()
            conteo_fecha = evolucion_por_fecha.setdefault(
                fecha, {"abiertas": 0, "resueltas": 0}
            )
            clave_estado = (
                "resueltas"
                if emergencia.estado == EstadoEmergencia.RESUELTA
                else "abiertas"
            )
            conteo_fecha[clave_estado] += 1
            cantidad_total_necesidades += sum(
                lote.cantidad for lote in emergencia.lotes
            )
            fecha_registro = emergencia.fecha_hora_registro
            if fecha_registro.tzinfo is None:
                fecha_registro = fecha_registro.replace(tzinfo=timezone.utc)
            tiempo_total_horas += (
                ahora - fecha_registro
            ).total_seconds() / 3600

        ofertas = (
            db.query(OfertaAyuda)
            .options(
                selectinload(OfertaAyuda.items),
                selectinload(OfertaAyuda.organizacion),
                selectinload(OfertaAyuda.items)
                .selectinload(OfertaItem.lote_necesidad)
                .selectinload(LoteNecesidad.referencia_cloud),
            )
            .all()
        )
        emergencias_filtradas = {emergencia.id for emergencia in emergencias}
        ofertas = [oferta for oferta in ofertas if oferta.emergencia_id in emergencias_filtradas]
        ofertas_adjudicadas = [oferta for oferta in ofertas if oferta.adjudicada_en]
        ofertas_conjuntas = sum(
            1 for oferta in ofertas_adjudicadas if oferta.es_conjunta
        )
        recursos_adjudicados: dict[tuple[str, int | None, str], int] = {}
        demanda_oferta: dict[tuple[str, int | None], dict[str, int]] = {}
        for emergencia in emergencias:
            for lote in emergencia.lotes:
                recurso_id = lote.tipo_recurso_id
                clave = (lote.tipo, recurso_id)
                registro = demanda_oferta.setdefault(
                    clave,
                    {"cantidad_requerida": 0, "cantidad_ofrecida": 0},
                )
                registro["cantidad_requerida"] += lote.cantidad
                registro["cantidad_ofrecida"] += sum(
                    item.cantidad_ofrecida
                    for item in lote.items
                )
        for oferta in ofertas_adjudicadas:
            mes = oferta.adjudicada_en.astimezone(timezone.utc).strftime("%Y-%m")
            for item in oferta.items:
                lote = item.lote_necesidad
                clave = (mes, lote.tipo_recurso_id, lote.tipo)
                recursos_adjudicados[clave] = (
                    recursos_adjudicados.get(clave, 0) + item.cantidad_ofrecida
                )
        capacidades_por_ong: dict[int, dict[str, int | str]] = {}
        for oferta in ofertas:
            if oferta.adjudicada_en is None:
                continue
            organizacion = oferta.organizacion
            capacidades = sum(
                item.cantidad_ofrecida for item in oferta.items
            )
            registro = capacidades_por_ong.setdefault(
                oferta.organizacion_id,
                {
                    "organizacion_id": oferta.organizacion_id,
                    "organizacion_nombre": organizacion.nombre,
                    "cantidad_capacidades_asignadas": 0,
                },
            )
            registro["cantidad_capacidades_asignadas"] += capacidades
        ranking_ongs = [
            RankingONG.model_validate(registro)
            for registro in sorted(
                capacidades_por_ong.values(),
                key=lambda registro: (
                    -int(registro["cantidad_capacidades_asignadas"]),
                    int(registro["organizacion_id"]),
                ),
            )
        ]
        return EmergenciasDashboard(
            total=len(emergencias),
            conteos_por_estado=conteos_por_estado,
            emergencias_activas=len(emergencias) - emergencias_resueltas,
            emergencias_resueltas=emergencias_resueltas,
            evolucion_abiertas_resueltas=[
                EvolucionEmergencias(fecha=fecha, **conteos)
                for fecha, conteos in sorted(evolucion_por_fecha.items())
            ],
            ranking_ongs=ranking_ongs,
            cantidad_total_necesidades=cantidad_total_necesidades,
            tiempo_medio_vida_horas=(
                tiempo_total_horas / len(emergencias) if emergencias else 0.0
            ),
            emergencias=[EmergenciaRespuesta.model_validate(e) for e in emergencias],
            participacion_consorcios=ParticipacionConsorcios(
                total_ofertas_adjudicadas=len(ofertas_adjudicadas),
                ofertas_conjuntas_adjudicadas=ofertas_conjuntas,
                porcentaje_consorcios=(
                    ofertas_conjuntas * 100 / len(ofertas_adjudicadas)
                    if ofertas_adjudicadas else 0.0
                ),
            ),
            recursos_adjudicados_por_mes=[
                RecursoAdjudicadoPorMes(
                    mes=mes,
                    tipo_recurso=tipo,
                    tipo_recurso_id=recurso_id,
                    cantidad_adjudicada=cantidad,
                )
                for (mes, recurso_id, tipo), cantidad in sorted(
                    recursos_adjudicados.items()
                )
            ],
            demanda_vs_oferta_por_recurso=[
                DemandaOfertaRecurso(
                    tipo_recurso=tipo,
                    tipo_recurso_id=recurso_id,
                    **cantidades,
                )
                for (tipo, recurso_id), cantidades in sorted(
                    demanda_oferta.items(),
                    key=lambda item: (item[0][0], item[0][1] is not None, item[0][1] or 0),
                )
            ],
            emergencias_por_estado_y_gravedad=[
                EmergenciasPorEstadoGravedad(
                    estado=estado,
                    nivel_gravedad=gravedad,
                    cantidad=cantidad,
                )
                for (estado, gravedad), cantidad in sorted(
                    emergencias_por_estado_y_gravedad.items()
                )
            ],
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

    async def crear_emergencia(
        self,
        db: Session,
        data: EmergenciaCrear,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> EmergenciaRespuesta:
        try:
            prioridad = await prioridad_client.obtener_prioridad(
                data.nivel_gravedad, data.zona_afectada
            )
        except PrioridadClientError as exc:
            logger.error(
                "No se pudo obtener la prioridad de la emergencia: %s", exc
            )
            raise HTTPException(
                status_code=503,
                detail="No se pudo obtener la prioridad de la emergencia",
            )

        emergencia = Emergencia(**data.model_dump(), prioridad=prioridad)
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

        Envía las cinco variables como entradas del contrato de instanciación;
        el proceso las usa para inicializar sus variables de caso.
        Puede iniciarse sin lotes; la publicación exige cargarlos.

        Es idempotente: si la emergencia ya tiene un caso, devuelve el mismo.
        """
        # La espera del bloqueo no debe impedir que otra petición termine su HTTP.
        emergencia = await run_in_threadpool(
            self._obtener_emergencia_entidad, db, emergencia_id, bloquear=True
        )

        # Idempotencia: si ya tiene caso, no crear otro
        if emergencia.bonita_case_id:
            return int(emergencia.bonita_case_id)

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

        # Persistir sólo tras la instanciación exitosa para permitir reintentos
        # cuando Bonita rechaza la solicitud.
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
