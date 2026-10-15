export interface RecursoInventario {
  id: number
  organizacion_id: number
  tipo: string
  cantidad_total: number
  unidad: string | null
  descripcion: string | null
}

export interface RecursoInventarioRequest {
  tipo: string
  cantidad_total: number
  unidad?: string | null
  descripcion?: string | null
}
