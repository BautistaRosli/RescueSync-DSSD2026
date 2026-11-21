export interface RecursoCloud {
  id: number
  nombre: string
  descripcion: string | null
}

export interface RecursoCloudCreateRequest {
  nombre: string
  descripcion?: string | null
}
