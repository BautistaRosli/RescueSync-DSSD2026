export interface ReporteEmergenciaGravedad {
  estado: string
  nivel_gravedad: string
  cantidad: number
}

export interface ReporteSuministroMovilizado {
  mes: string
  tipo_recurso: string
  cantidad_adjudicada: number
}

export interface ReporteConsorcios {
  total_ofertas_adjudicadas: number
  ofertas_conjuntas: number
  porcentaje_consorcios: number
}

export interface ReporteProyecto {
  emergencia_id: number
  zona_afectada: string
  items_totales: number
  items_finalizados: number
  items_pendientes: number
  resuelta: boolean
}

export interface ReporteCoberturaLote {
  lote_id: number
  emergencia_id: number
  tipo_recurso: string
  cantidad_requerida: number
  cantidad_ofrecida: number
  porcentaje_cobertura: number
}

export interface ReporteCoberturaLotes {
  lotes: ReporteCoberturaLote[]
  lotes_sin_cubrir: ReporteCoberturaLote[]
}

export interface ReporteTiempoPublicacion {
  promedio_horas: number
  minimo_horas: number
  maximo_horas: number
}

export interface ReporteTiempoAdjudicacion {
  promedio_horas: number
}

export interface ReporteRankingOng {
  organizacion_id: number
  organizacion_nombre: string
  ofertas_presentadas: number
  ofertas_adjudicadas: number
  participaciones_consorcios: number
  actividades_finalizadas: number
}

export interface ReporteDemandaOferta {
  tipo_recurso: string
  cantidad_pedida: number
  cantidad_ofrecida: number
}
