import { apiGet, apiPost, establecerTokenSesion, leerTokenSesion } from './http'
import { listarRoles } from './rol'
import type { AuthResponse, LoginRequest, RegistroRequest, UsuarioRead } from '../types'

const TOKEN_TYPE = 'bearer'

export async function registrar(datos: RegistroRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/registro', datos)
}

export async function iniciarSesion(datos: LoginRequest): Promise<AuthResponse> {
  const sesion = await apiPost<AuthResponse>('/auth/login', datos)
  establecerTokenSesion(sesion.access_token)
  return sesion
}

/**
 * Reconstruye la sesión a partir del token persistido pidiendo los datos al backend.
 * Si el token no es válido o el usuario está inactivo, limpia el token y devuelve null.
 */
export async function restaurarSesion(): Promise<AuthResponse | null> {
  const token = leerTokenSesion()
  if (token === null) {
    return null
  }

  try {
    const usuario = await apiGet<UsuarioRead>('/auth/me')
    const roles = await listarRoles()
    const rol = roles.find((item) => item.id === usuario.rol_id)
    if (rol === undefined) {
      establecerTokenSesion(null)
      return null
    }
    return {
      access_token: token,
      token_type: TOKEN_TYPE,
      rol: rol.nombre,
      usuario,
    }
  } catch {
    establecerTokenSesion(null)
    return null
  }
}

export function cerrarSesion(): void {
  establecerTokenSesion(null)
}