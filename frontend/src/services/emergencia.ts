import { apiGet, apiPost } from './http'
import type {
  EmergenciaCreateRequest,
  EmergenciaCreada,
  EmergenciaRead,
} from '../types'

export async function registrarEmergencia(
  datos: EmergenciaCreateRequest,
): Promise<EmergenciaCreada> {
  return apiPost<EmergenciaCreada>('/emergencias', datos)
}

export async function listarEmergencias(): Promise<EmergenciaRead[]> {
  return apiGet<EmergenciaRead[]>('/emergencias')
}

export async function obtenerEmergencia(
  emergenciaId: number,
): Promise<EmergenciaRead> {
  return apiGet<EmergenciaRead>(`/emergencias/${emergenciaId}`)
}
