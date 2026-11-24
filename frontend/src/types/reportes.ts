import type {
  DemandaVsOfertaPorRecurso,
  EmergenciaPorEstadoYGravedad,
  EvolucionAbiertasResueltas,
  ParticipacionConsorcios,
  RankingOng,
  RecursoAdjudicadoPorMes,
} from './emergencia'

export interface ReporteEmergenciaGravedad {
  estado: string
  nivel_gravedad: string
  cantidad: number
}
export interface ReporteSuministroMovilizado { mes: string; tipo_recurso: string; cantidad_adjudicada: number }
export interface ReporteConsorcios { total_ofertas_adjudicadas: number; ofertas_conjuntas: number; porcentaje_consorcios: number }
export interface ReporteProyecto { emergencia_id: number; zona_afectada: string; items_totales: number; items_finalizados: number; items_pendientes: number; resuelta: boolean }
export interface ReporteCoberturaLote { lote_id: number; emergencia_id: number; tipo_recurso: string; cantidad_requerida: number; cantidad_ofrecida: number; porcentaje_cobertura: number }
export interface ReporteCoberturaLotes { lotes: ReporteCoberturaLote[]; lotes_sin_cubrir: ReporteCoberturaLote[] }
export interface ReporteTiempoPublicacion { promedio_horas: number; minimo_horas: number; maximo_horas: number }
export interface ReporteTiempoAdjudicacion { promedio_horas: number }
export interface ReporteRankingOng { organizacion_id: number; organizacion_nombre: string; ofertas_presentadas: number; ofertas_adjudicadas: number; participaciones_consorcios: number; actividades_finalizadas: number }
export interface ReporteDemandaOferta { tipo_recurso: string; cantidad_pedida: number; cantidad_ofrecida: number }

export interface FiltrosReportes {
  desde?: string
  hasta?: string
  nivel_gravedad?: 'baja' | 'media' | 'alta' | 'critica'
}
export type FormatoReporte = 'csv' | 'json'
export interface ActivasResueltas { activas: number; resueltas: number }
export interface NecesidadActual { tipo_recurso: string; tipo_recurso_id: number | null; cantidad_requerida: number }
export interface TiempoVida { promedio_horas: number }
export interface PrioridadAbiertas { promedio_prioridad: number; cantidad_emergencias: number }
export interface ReportesDashboard {
  emergencias: EmergenciaPorEstadoYGravedad[]
  activas_resueltas: ActivasResueltas
  evolucion_abiertas_resueltas: EvolucionAbiertasResueltas[]
  necesidades_actuales: NecesidadActual[]
  suministros_movilizados: RecursoAdjudicadoPorMes[]
  consorcios: ParticipacionConsorcios
  demanda_oferta: DemandaVsOfertaPorRecurso[]
  ranking_ongs: RankingOng[]
  tiempo_vida: TiempoVida
  prioridad_abiertas: PrioridadAbiertas
}
