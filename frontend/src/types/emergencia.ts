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

export interface EmergenciaRead {
  id: number
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
  tipo_desastre: string | null
  fecha_hora_registro: string
  publicada: boolean
  fecha_publicacion: string | null
  estado: EstadoEmergencia | null
  bonita_case_id: string | null
}
