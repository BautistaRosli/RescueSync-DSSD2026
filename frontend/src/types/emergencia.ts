export type NivelGravedad = 'baja' | 'media' | 'alta' | 'critica'

export type EstadoEmergencia =
  | 'esperando_lotes'
  | 'esperando_ofertas'
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
}

export interface LoteNecesidad {
  id: number
  emergencia_id: number
  tipo: string
  cantidad: number
  unidad: string | null
  descripcion: string | null
}

export interface LoteNecesidadCreateRequest {
  tipo: string
  cantidad: number
  unidad?: string | null
  descripcion?: string | null
}

// Espejo de `LoteNecesidadActualizar`: PATCH parcial, los cuatro campos son opcionales.
export interface LoteNecesidadUpdateRequest {
  tipo?: string
  cantidad?: number
  unidad?: string | null
  descripcion?: string | null
}

export interface BandaEmergenciasParams {
  publicada: boolean
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
  // Ventana de convocatoria: todavía no existe en el backend (la agrega otro
  // integrante del equipo). Opcionales para que la UI funcione sin ellas.
  fecha_apertura_convocatoria?: string | null
  fecha_cierre_convocatoria?: string | null
  lotes: LoteNecesidad[]
}

// Sobre del `GET /emergencias/bandeja`: `paginas` es 0 cuando `total` es 0.
export interface BandaEmergencias {
  items: EmergenciaRead[]
  pagina: number
  por_pagina: number
  total: number
  paginas: number
}
