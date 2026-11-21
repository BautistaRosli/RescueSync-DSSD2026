from sqlalchemy.orm import Session

from ..dto.emergencias_dto import (
    DemandaOfertaRecurso,
    EmergenciasPorEstadoGravedad,
    ParticipacionConsorcios,
    RankingONG,
    RecursoAdjudicadoPorMes,
)
from ..dto.reportes_dto import (
    ActivasResueltas,
    NecesidadActual,
    PrioridadAbiertas,
    TiempoVida,
)
from ..models import EstadoEmergencia
from .emergencias_service import EmergenciaService


class ReportesService:
    """Expone el contrato de reportes reutilizando el dashboard existente."""

    def __init__(self) -> None:
        self._emergencias = EmergenciaService()

    def obtener_emergencias(
        self, db: Session
    ) -> list[EmergenciasPorEstadoGravedad]:
        return self._emergencias.obtener_dashboard(
            db
        ).emergencias_por_estado_y_gravedad

    def obtener_suministros_movilizados(
        self, db: Session
    ) -> list[RecursoAdjudicadoPorMes]:
        return self._emergencias.obtener_dashboard(
            db
        ).recursos_adjudicados_por_mes

    def obtener_consorcios(self, db: Session) -> ParticipacionConsorcios:
        return self._emergencias.obtener_dashboard(db).participacion_consorcios

    def obtener_ranking_ongs(self, db: Session) -> list[RankingONG]:
        return self._emergencias.obtener_dashboard(db).ranking_ongs

    def obtener_demanda_oferta(
        self, db: Session
    ) -> list[DemandaOfertaRecurso]:
        return self._emergencias.obtener_dashboard(
            db
        ).demanda_vs_oferta_por_recurso

    def obtener_activas_resueltas(self, db: Session) -> ActivasResueltas:
        dashboard = self._emergencias.obtener_dashboard(db)
        return ActivasResueltas(
            activas=dashboard.emergencias_activas,
            resueltas=dashboard.emergencias_resueltas,
        )

    def obtener_evolucion_abiertas_resueltas(self, db: Session):
        return self._emergencias.obtener_dashboard(db).evolucion_abiertas_resueltas

    def obtener_necesidades_actuales(self, db: Session) -> list[NecesidadActual]:
        dashboard = self._emergencias.obtener_dashboard(db)
        acumuladas: dict[tuple[str, int | None], int] = {}
        for emergencia in dashboard.emergencias:
            if emergencia.estado == EstadoEmergencia.RESUELTA:
                continue
            for lote in emergencia.lotes:
                clave = (lote.tipo, lote.tipo_recurso_id)
                acumuladas[clave] = acumuladas.get(clave, 0) + lote.cantidad
        return [
            NecesidadActual(
                tipo_recurso=tipo,
                tipo_recurso_id=recurso_id,
                cantidad_requerida=cantidad,
            )
            for (tipo, recurso_id), cantidad in sorted(
                acumuladas.items(), key=lambda item: (item[0][0], item[0][1] or 0)
            )
        ]

    def obtener_tiempo_vida(self, db: Session) -> TiempoVida:
        dashboard = self._emergencias.obtener_dashboard(db)
        return TiempoVida(promedio_horas=dashboard.tiempo_medio_vida_horas)

    def obtener_prioridad_abiertas(self, db: Session) -> PrioridadAbiertas:
        dashboard = self._emergencias.obtener_dashboard(db)
        prioridades = [
            emergencia.prioridad
            for emergencia in dashboard.emergencias
            if emergencia.estado != EstadoEmergencia.RESUELTA
            and emergencia.prioridad is not None
        ]
        return PrioridadAbiertas(
            promedio_prioridad=(sum(prioridades) / len(prioridades) if prioridades else 0.0),
            cantidad_emergencias=len(prioridades),
        )
