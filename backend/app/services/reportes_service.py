from datetime import datetime

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
        self, db: Session, desde: datetime | None = None,
        hasta: datetime | None = None, nivel_gravedad: str | None = None,
    ) -> list[EmergenciasPorEstadoGravedad]:
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).emergencias_por_estado_y_gravedad

    def obtener_suministros_movilizados(
        self, db: Session, desde: datetime | None = None,
        hasta: datetime | None = None, nivel_gravedad: str | None = None,
    ) -> list[RecursoAdjudicadoPorMes]:
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).recursos_adjudicados_por_mes

    def obtener_consorcios(self, db: Session, desde: datetime | None = None,
                           hasta: datetime | None = None,
                           nivel_gravedad: str | None = None) -> ParticipacionConsorcios:
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).participacion_consorcios

    def obtener_ranking_ongs(self, db: Session, desde: datetime | None = None,
                             hasta: datetime | None = None,
                             nivel_gravedad: str | None = None) -> list[RankingONG]:
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).ranking_ongs

    def obtener_demanda_oferta(
        self, db: Session, desde: datetime | None = None,
        hasta: datetime | None = None, nivel_gravedad: str | None = None,
    ) -> list[DemandaOfertaRecurso]:
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).demanda_vs_oferta_por_recurso

    def obtener_activas_resueltas(self, db: Session, desde: datetime | None = None,
                                  hasta: datetime | None = None,
                                  nivel_gravedad: str | None = None) -> ActivasResueltas:
        dashboard = self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        )
        return ActivasResueltas(
            activas=dashboard.emergencias_activas,
            resueltas=dashboard.emergencias_resueltas,
        )

    def obtener_evolucion_abiertas_resueltas(self, db: Session, desde: datetime | None = None,
                                             hasta: datetime | None = None,
                                             nivel_gravedad: str | None = None):
        return self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        ).evolucion_abiertas_resueltas

    def obtener_necesidades_actuales(self, db: Session, desde: datetime | None = None,
                                     hasta: datetime | None = None,
                                     nivel_gravedad: str | None = None) -> list[NecesidadActual]:
        dashboard = self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        )
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

    def obtener_tiempo_vida(self, db: Session, desde: datetime | None = None,
                            hasta: datetime | None = None,
                            nivel_gravedad: str | None = None) -> TiempoVida:
        dashboard = self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        )
        return TiempoVida(promedio_horas=dashboard.tiempo_medio_vida_horas)

    def obtener_prioridad_abiertas(self, db: Session, desde: datetime | None = None,
                                   hasta: datetime | None = None,
                                   nivel_gravedad: str | None = None) -> PrioridadAbiertas:
        dashboard = self._emergencias.obtener_dashboard(
            db, desde=desde, hasta=hasta, nivel_gravedad=nivel_gravedad
        )
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

    def obtener_reporte_completo(
        self, db: Session, desde: datetime | None = None,
        hasta: datetime | None = None, nivel_gravedad: str | None = None,
    ) -> dict[str, object]:
        """Devuelve todas las métricas exportables con el mismo filtro."""
        return {
            "emergencias_por_estado_y_gravedad": self.obtener_emergencias(
                db, desde, hasta, nivel_gravedad
            ),
            "recursos_adjudicados_por_mes": self.obtener_suministros_movilizados(
                db, desde, hasta, nivel_gravedad
            ),
            "participacion_consorcios": self.obtener_consorcios(
                db, desde, hasta, nivel_gravedad
            ),
            "ranking_ongs": self.obtener_ranking_ongs(
                db, desde, hasta, nivel_gravedad
            ),
            "demanda_vs_oferta_por_recurso": self.obtener_demanda_oferta(
                db, desde, hasta, nivel_gravedad
            ),
            "emergencias_activas_vs_resueltas": self.obtener_activas_resueltas(
                db, desde, hasta, nivel_gravedad
            ),
            "evolucion_abiertas_y_resueltas": self.obtener_evolucion_abiertas_resueltas(
                db, desde, hasta, nivel_gravedad
            ),
            "necesidades_actuales": self.obtener_necesidades_actuales(
                db, desde, hasta, nivel_gravedad
            ),
            "tiempo_medio_de_vida": self.obtener_tiempo_vida(
                db, desde, hasta, nivel_gravedad
            ),
            "promedio_prioridad_abiertas": self.obtener_prioridad_abiertas(
                db, desde, hasta, nivel_gravedad
            ),
        }
