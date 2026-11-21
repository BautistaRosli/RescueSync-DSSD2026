import { apiDescargar, apiGet } from './http'
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

import type { FiltrosReportes, FormatoReporte } from '../types'

function construirConsulta(filtros: FiltrosReportes = {}, formato?: FormatoReporte): string {
  const consulta = new URLSearchParams()
  if (filtros.desde) consulta.set('desde', `${filtros.desde}T00:00:00`)
  if (filtros.hasta) consulta.set('hasta', `${filtros.hasta}T23:59:59`)
  if (filtros.nivel_gravedad) consulta.set('nivel_gravedad', filtros.nivel_gravedad)
  if (formato) consulta.set('formato', formato)
  const texto = consulta.toString()
  return texto ? `?${texto}` : ''
}

export function exportarReporteCompleto(filtros: FiltrosReportes, formato: FormatoReporte): Promise<Blob> {
  return apiDescargar(`/reportes/exportar${construirConsulta(filtros, formato)}`)
}

export const obtenerEmergenciasPorEstadoYGravedad = (filtros?: FiltrosReportes): Promise<EmergenciaPorEstadoYGravedad[]> =>
  apiGet<EmergenciaPorEstadoYGravedad[]>(`/reportes/emergencias${construirConsulta(filtros)}`)

export const obtenerActivasResueltas = (filtros?: FiltrosReportes): Promise<ActivasResueltas> =>
  apiGet<ActivasResueltas>(`/reportes/activas-resueltas${construirConsulta(filtros)}`)

export const obtenerEvolucionAbiertasResueltas = (filtros?: FiltrosReportes): Promise<EvolucionAbiertasResueltas[]> =>
  apiGet<EvolucionAbiertasResueltas[]>(`/reportes/evolucion-abiertas-resueltas${construirConsulta(filtros)}`)

export const obtenerNecesidadesActuales = (filtros?: FiltrosReportes): Promise<NecesidadActual[]> =>
  apiGet<NecesidadActual[]>(`/reportes/necesidades-actuales${construirConsulta(filtros)}`)

export const obtenerSuministrosMovilizados = (filtros?: FiltrosReportes): Promise<RecursoAdjudicadoPorMes[]> =>
  apiGet<RecursoAdjudicadoPorMes[]>(`/reportes/suministros-movilizados${construirConsulta(filtros)}`)

export const obtenerParticipacionConsorcios = (filtros?: FiltrosReportes): Promise<ParticipacionConsorcios> =>
  apiGet<ParticipacionConsorcios>(`/reportes/consorcios${construirConsulta(filtros)}`)

export const obtenerDemandaOferta = (filtros?: FiltrosReportes): Promise<DemandaVsOfertaPorRecurso[]> =>
  apiGet<DemandaVsOfertaPorRecurso[]>(`/reportes/demanda-oferta${construirConsulta(filtros)}`)

export const obtenerRankingOngs = (filtros?: FiltrosReportes): Promise<RankingOng[]> =>
  apiGet<RankingOng[]>(`/reportes/ranking-ongs${construirConsulta(filtros)}`)

export const obtenerTiempoVida = (filtros?: FiltrosReportes): Promise<TiempoVida> =>
  apiGet<TiempoVida>(`/reportes/tiempo-vida${construirConsulta(filtros)}`)

export const obtenerPrioridadAbiertas = (filtros?: FiltrosReportes): Promise<PrioridadAbiertas> =>
  apiGet<PrioridadAbiertas>(`/reportes/prioridad-abiertas${construirConsulta(filtros)}`)
