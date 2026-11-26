export interface RecursoInventario {
  id: number
  organizacion_id: number
  tipo: string
  cantidad_total: number
  unidad: string | null
  descripcion: string | null
  tipo_recurso_id: number | null
  comprometido: number | null
  disponible: number | null
  sincronizado: boolean
}

export interface RecursoInventarioRequest {
  tipo_recurso_id: number
  cantidad_total: number
  unidad?: string | null
  descripcion?: string | null
}

export interface RecursoInventarioUpdateRequest {
  cantidad_total: number
  unidad?: string | null
  descripcion?: string | null
  tipo_recurso_id?: number
}
