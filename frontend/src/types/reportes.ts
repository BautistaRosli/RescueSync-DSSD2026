import type {
  DemandaVsOfertaPorRecurso,
  EmergenciaPorEstadoYGravedad,
  EvolucionAbiertasResueltas,
  ParticipacionConsorcios,
  RankingOng,
  RecursoAdjudicadoPorMes,
} from './emergencia'

export interface ActivasResueltas {
  activas: number
  resueltas: number
}

export interface NecesidadActual {
  tipo_recurso: string
  tipo_recurso_id: number | null
  cantidad_requerida: number
}

export interface TiempoVida {
  promedio_horas: number
}

export interface PrioridadAbiertas {
  promedio_prioridad: number
  cantidad_emergencias: number
}

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
