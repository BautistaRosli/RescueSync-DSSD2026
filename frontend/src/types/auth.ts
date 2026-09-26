export interface UsuarioRead {
  id: number
  email: string
  nombre: string
  apellido: string
  rol_id: number
  activo: boolean
  municipio_id: number | null
  organizacion_id: number | null
}

export interface AuthResponse {
  access_token: string
  token_type: string
  rol: string
  usuario: UsuarioRead
}

export interface RegistroRequest {
  email: string
  password: string
  nombre: string
  apellido: string
  rol_id: number
  municipio_id?: number | null
  organizacion_id?: number | null
}

export interface LoginRequest {
  email: string
  password: string
}
