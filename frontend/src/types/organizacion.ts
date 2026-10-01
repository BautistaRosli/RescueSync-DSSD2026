export interface OrganizacionRead {
  id: number
  nombre: string
  tipo: string
  email: string | null
  telefono: string | null
  activa: boolean
}

export interface OrganizacionCreateRequest {
  nombre: string
  tipo: string
  email?: string | null
  telefono?: string | null
}

// Datos mínimos de una ONG participante de una oferta (consorcio).
export interface OrganizacionResumen {
  id: number
  nombre: string
}
