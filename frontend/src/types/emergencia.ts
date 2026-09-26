export type NivelGravedad = 'baja' | 'media' | 'alta' | 'critica'

export interface EmergenciaCreateRequest {
  municipio_id: number
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
}

// Subconjunto del `EmergenciaRead` del backend: solo los campos que muestra la UI.
export interface EmergenciaCreada {
  id: number
  municipio_id: number
  nivel_gravedad: NivelGravedad
  zona_afectada: string
  descripcion_inicial: string
  fecha_hora_registro: string
  publicada: boolean
}
