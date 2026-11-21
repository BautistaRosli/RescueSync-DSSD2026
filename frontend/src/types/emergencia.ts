export type NivelGravedad = 'baja' | 'media' | 'alta' | 'critica'

export type EstadoEmergencia =
  | 'esperando_lotes'
  | 'esperando_ofertas'
  | 'esperando_adjudicacion'
  | 'en_proceso'
  | 'resuelta'

export interface EmergenciaCreateRequest {
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
}

// Subconjunto del `EmergenciaRespuesta` del backend: solo los campos que muestra la UI.
export interface EmergenciaCreada {
  id: number
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
  fecha_hora_registro: string
  publicada: boolean
  prioridad?: number | null
}

export interface LoteNecesidad {
  id: number
  emergencia_id: number
  tipo: string
  cantidad: number
  unidad: string | null
  descripcion: string | null
  tipo_recurso_id: number | null
}

export interface LoteNecesidadCreateRequest {
  tipo: string
  cantidad: number
  unidad?: string | null
  descripcion?: string | null
  tipo_recurso_id?: number | null
}

// Espejo de `LoteNecesidadActualizar`: PATCH parcial, todos los campos son opcionales.
export interface LoteNecesidadUpdateRequest {
  tipo?: string
  cantidad?: number
  unidad?: string | null
  descripcion?: string | null
  tipo_recurso_id?: number | null
}

export interface BandaEmergenciasParams {
  publicada?: boolean
  estado?: EstadoEmergencia
  pagina: number
  por_pagina: number
}

// Subconjunto del `EmergenciaRespuesta` del backend: solo los campos que muestra la UI.
export interface EmergenciaRead {
  id: number
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
  fecha_hora_registro: string
  publicada: boolean
  fecha_publicacion: string | null
  estado: EstadoEmergencia | null
  bonita_case_id: string | null
  prioridad?: number | null
  // Ventana de convocatoria: todavía no existe en el backend (la agrega otro
  // integrante del equipo). Opcionales para que la UI funcione sin ellas.
  fecha_apertura_convocatoria?: string | null
  fecha_cierre_convocatoria?: string | null
  lotes: LoteNecesidad[]
}

export type EmergenciaRespuesta = EmergenciaRead

export interface RankingOng {
  organizacion_id: number
  organizacion_nombre: string
  cantidad_capacidades_asignadas: number
}

export interface EvolucionAbiertasResueltas {
  fecha: string
  abiertas: number
  resueltas: number
}

export interface ParticipacionConsorcios {
  total_ofertas_adjudicadas: number
  ofertas_conjuntas_adjudicadas: number
  porcentaje_consorcios: number
}

export interface RecursoAdjudicadoPorMes {
  mes: string
  tipo_recurso: string
  tipo_recurso_id: number | null
  cantidad_adjudicada: number
}

export interface DemandaVsOfertaPorRecurso {
  tipo_recurso: string
  tipo_recurso_id: number | null
  cantidad_requerida: number
  cantidad_ofrecida: number
}

export interface EmergenciaPorEstadoYGravedad {
  estado: string
  nivel_gravedad: string
  cantidad: number
}

export interface DashboardEmergencias {
  total: number
  conteos_por_estado: Record<string, number>
  emergencias: EmergenciaRespuesta[]
  emergencias_activas: number
  emergencias_resueltas: number
  evolucion_abiertas_resueltas: EvolucionAbiertasResueltas[]
  ranking_ongs: RankingOng[]
  cantidad_total_necesidades: number
  tiempo_medio_vida_horas: number
  participacion_consorcios: ParticipacionConsorcios
  recursos_adjudicados_por_mes: RecursoAdjudicadoPorMes[]
  demanda_vs_oferta_por_recurso: DemandaVsOfertaPorRecurso[]
  emergencias_por_estado_y_gravedad: EmergenciaPorEstadoYGravedad[]
  necesidades_actuales: Array<{
    tipo_recurso: string
    tipo_recurso_id: number | null
    cantidad_requerida: number
  }>
  prioridad_abiertas: {
    promedio_prioridad: number
    cantidad_emergencias: number
  }
}

// Sobre del `GET /emergencias/bandeja`: `paginas` es 0 cuando `total` es 0.
export interface BandaEmergencias {
  items: EmergenciaRead[]
  pagina: number
  por_pagina: number
  total: number
  paginas: number
}
