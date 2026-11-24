import { apiGet, apiPost } from './http'
import type { RecursoCloud, RecursoCloudCreateRequest } from '../types'

export async function listarRecursosCloud(texto: string): Promise<RecursoCloud[]> {
  const consulta = texto.trim()
  if (!consulta) {
    return []
  }
  return apiGet<RecursoCloud[]>(`/recursos-cloud?texto=${encodeURIComponent(consulta)}`)
}

export async function crearRecursoCloud(
  datos: RecursoCloudCreateRequest,
): Promise<RecursoCloud> {
  return apiPost<RecursoCloud>('/recursos-cloud', datos)
}
