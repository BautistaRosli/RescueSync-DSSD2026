export interface NotificacionAdjudicacion {
  id: number
  oferta_id: number
  emergencia_id: number
  zona_afectada: string
  lotes_adjudicados: string[]
  fecha_hora: string
  leida: boolean
}

export interface ActividadFinalizada {
  lote_necesidad_id: number
  fecha_hora: string
}
