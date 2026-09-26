import { apiPost } from './http'
import type { EmergenciaCreateRequest, EmergenciaCreada } from '../types'

export async function registrarEmergencia(
  datos: EmergenciaCreateRequest,
): Promise<EmergenciaCreada> {
  return apiPost<EmergenciaCreada>('/emergencias', datos)
}
