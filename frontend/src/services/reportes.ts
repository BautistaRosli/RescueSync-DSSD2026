import { apiGet } from './http'
import type {
  ReporteCoberturaLotes,
  ReporteConsorcios,
  ReporteDemandaOferta,
  ReporteEmergenciaGravedad,
  ReporteProyecto,
  ReporteRankingOng,
  ReporteSuministroMovilizado,
  ReporteTiempoAdjudicacion,
  ReporteTiempoPublicacion,
} from '../types'

export const obtenerReporteEmergencias = () =>
  apiGet<ReporteEmergenciaGravedad[]>('/reportes/emergencias')

export const obtenerReporteSuministrosMovilizados = () =>
  apiGet<ReporteSuministroMovilizado[]>('/reportes/suministros-movilizados')

export const obtenerReporteConsorcios = () =>
  apiGet<ReporteConsorcios>('/reportes/consorcios')

export const obtenerReporteProyectos = () =>
  apiGet<ReporteProyecto[]>('/reportes/proyectos')

export const obtenerReporteCoberturaLotes = () =>
  apiGet<ReporteCoberturaLotes>('/reportes/cobertura-lotes')

export const obtenerReporteTiempoPublicacion = () =>
  apiGet<ReporteTiempoPublicacion>('/reportes/tiempo-publicacion')

export const obtenerReporteTiempoAdjudicacion = () =>
  apiGet<ReporteTiempoAdjudicacion>('/reportes/tiempo-adjudicacion')

export const obtenerReporteRankingOngs = () =>
  apiGet<ReporteRankingOng[]>('/reportes/ranking-ongs')

export const obtenerReporteDemandaOferta = () =>
  apiGet<ReporteDemandaOferta[]>('/reportes/demanda-oferta')
