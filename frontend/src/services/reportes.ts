import { apiGet } from './http'
import type {
  ActivasResueltas,
  DemandaVsOfertaPorRecurso,
  EmergenciaPorEstadoYGravedad,
  EvolucionAbiertasResueltas,
  NecesidadActual,
  ParticipacionConsorcios,
  PrioridadAbiertas,
  RankingOng,
  RecursoAdjudicadoPorMes,
  TiempoVida,
} from '../types'

export const obtenerEmergenciasPorEstadoYGravedad = (): Promise<EmergenciaPorEstadoYGravedad[]> =>
  apiGet<EmergenciaPorEstadoYGravedad[]>('/reportes/emergencias')

export const obtenerActivasResueltas = (): Promise<ActivasResueltas> =>
  apiGet<ActivasResueltas>('/reportes/activas-resueltas')

export const obtenerEvolucionAbiertasResueltas = (): Promise<EvolucionAbiertasResueltas[]> =>
  apiGet<EvolucionAbiertasResueltas[]>('/reportes/evolucion-abiertas-resueltas')

export const obtenerNecesidadesActuales = (): Promise<NecesidadActual[]> =>
  apiGet<NecesidadActual[]>('/reportes/necesidades-actuales')

export const obtenerSuministrosMovilizados = (): Promise<RecursoAdjudicadoPorMes[]> =>
  apiGet<RecursoAdjudicadoPorMes[]>('/reportes/suministros-movilizados')

export const obtenerParticipacionConsorcios = (): Promise<ParticipacionConsorcios> =>
  apiGet<ParticipacionConsorcios>('/reportes/consorcios')

export const obtenerDemandaOferta = (): Promise<DemandaVsOfertaPorRecurso[]> =>
  apiGet<DemandaVsOfertaPorRecurso[]>('/reportes/demanda-oferta')

export const obtenerRankingOngs = (): Promise<RankingOng[]> =>
  apiGet<RankingOng[]>('/reportes/ranking-ongs')

export const obtenerTiempoVida = (): Promise<TiempoVida> =>
  apiGet<TiempoVida>('/reportes/tiempo-vida')

export const obtenerPrioridadAbiertas = (): Promise<PrioridadAbiertas> =>
  apiGet<PrioridadAbiertas>('/reportes/prioridad-abiertas')
