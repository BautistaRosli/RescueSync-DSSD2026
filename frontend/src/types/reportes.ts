import type { NivelGravedad } from './emergencia'

export interface FiltrosReportes {
  desde?: string
  hasta?: string
  nivel_gravedad?: NivelGravedad
}
export type FormatoReporte = 'csv' | 'json'

// Contrato de GET /reportes/tablero (espejo de backend/app/dto/tablero_dto.py).
export type FuenteIndicador =
  | 'local' | 'cloud' | 'bonita' | 'local+cloud' | 'local+bonita' | 'local+cloud+bonita'
export type AlcanceIndicador = 'filtrado' | 'global'

export interface Indicador {
  descripcion: string
  fuente: FuenteIndicador
  alcance: AlcanceIndicador
  emergencias_incluidas: number[]
}

export interface IndicadorConteo extends Indicador { valor: number }
export interface FilaEstadoGravedad { estado: string; nivel_gravedad: string; cantidad: number }
export interface IndicadorEstadoGravedad extends Indicador { filas: FilaEstadoGravedad[] }
export interface IndicadorPromedioValor extends Indicador { valor: number | null; n: number }
export interface IndicadorPromedioHoras extends Indicador { promedio: number | null; n: number }
export interface IndicadorResolucion extends IndicadorPromedioHoras {
  fuente_fecha: { local: number; bonita: number }
  sin_fecha_cierre: number[]
}
export interface FilaEvolucion { fecha: string; aperturas: number; cierres: number }
export interface IndicadorEvolucion extends Indicador { filas: FilaEvolucion[] }

export interface ResumenTablero {
  total: IndicadorConteo
  abiertas: IndicadorConteo
  resueltas: IndicadorConteo
  por_estado_y_gravedad: IndicadorEstadoGravedad
  prioridad_promedio_abiertas: IndicadorPromedioValor
  antiguedad_abiertas_horas: IndicadorPromedioHoras
  resolucion_horas: IndicadorResolucion
  evolucion: IndicadorEvolucion
}

export interface RecursoPorLote {
  lote_id: number
  emergencia_id: number
  tipo_recurso: string
  tipo_recurso_id: number | null
  unidad: string | null
  pedido: number
  ofertado: number
  verificado: number | null
  cubierto_confirmado: number
  porcentaje_cobertura: number | null
}
export interface TotalRecursoMes {
  mes: string | null
  tipo_recurso: string
  tipo_recurso_id: number | null
  unidad: string | null
  ofertado: number
  verificado: number
  reservado: number
  entregado: number
}
export interface RecursosTablero {
  por_lote: Indicador & { filas: RecursoPorLote[] }
  totales: Indicador & { filas: TotalRecursoMes[] }
  etiqueta_recursos: 'Recursos entregados' | 'Recursos reservados'
}

export interface CantidadPorUnidad { tipo_recurso: string; unidad: string | null; confirmado: number; entregado: number }
export interface ProyectoTablero {
  emergencia_id: number
  zona_afectada: string
  estado: string | null
  bonita_case_id: string | null
  items_totales: number
  items_finalizados: number
  cantidades: CantidadPorUnidad[]
  resuelta: boolean
  resolucion_horas: number | null
}
export interface IndicadorConsorcios extends Indicador {
  emergencias_resueltas: number
  resueltas_con_consorcio: number
  porcentaje: number | null
}
export interface FilaRankingOng {
  organizacion_id: number
  organizacion_nombre: string
  tipo_recurso: string
  unidad: string | null
  cantidad_confirmada: number
}
export interface ProyectosTablero {
  proyectos: Indicador & { filas: ProyectoTablero[] }
  consorcios: IndicadorConsorcios
  ranking_ongs: Indicador & { filas: FilaRankingOng[] }
}

export type EstadoCasoBonita = 'activo' | 'completed' | 'cancelado' | 'no_encontrado'
export interface TiempoEtapaBonita { etapa: string; promedio_horas: number | null; n: number }
export interface VerificacionCasoBonita {
  emergencia_id: number
  bonita_case_id: string
  estado_local: string | null
  estado_bonita: EstadoCasoBonita
  resolucion_horas: number | null
}
export interface BonitaTablero extends Indicador {
  disponible: boolean
  error: string | null
  casos_activos: number
  casos_finalizados: number
  casos_cancelados: number
  tiempos_por_etapa: TiempoEtapaBonita[]
  casos_camino_alternativo: number
  verificacion: VerificacionCasoBonita[]
}

export interface Tablero {
  generado_en: string
  filtros: { desde: string | null; hasta: string | null; nivel_gravedad: string | null }
  resumen: ResumenTablero
  recursos: RecursosTablero
  proyectos: ProyectosTablero
  bonita: BonitaTablero
}
