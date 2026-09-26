import { apiGet } from './http'
import type { Rol } from '../types'

export async function listarRoles(): Promise<Rol[]> {
  return apiGet<Rol[]>('/roles')
}
