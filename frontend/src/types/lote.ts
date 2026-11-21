export interface LoteRead {
  id: number
  emergencia_id: number
  tipo: string
  cantidad: number
  unidad: string | null
  descripcion: string | null
  tipo_recurso_id: number | null
}
