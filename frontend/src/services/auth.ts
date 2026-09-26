import { apiPost } from './http'
import type { AuthResponse, LoginRequest, RegistroRequest } from '../types'

export async function registrar(datos: RegistroRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/registro', datos)
}

export async function iniciarSesion(datos: LoginRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/login', datos)
}
