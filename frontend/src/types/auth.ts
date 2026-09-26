export type RolUsuario =
  | 'OPERADOR_MUNICIPAL'
  | 'CENTRO_COORDINADOR'
  | 'REPRESENTANTE_ONG'

export interface UsuarioRead {
  id: number
  email: string
  rol: string
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
  rol?: RolUsuario
  municipio_id?: number | null
  organizacion_id?: number | null
}

export interface LoginRequest {
  email: string
  password: string
}
