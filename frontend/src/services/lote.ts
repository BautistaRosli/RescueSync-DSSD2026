import { apiGet } from './http'
import type { LoteRead } from '../types'

export async function listarLotes(emergenciaId: number): Promise<LoteRead[]> {
  return apiGet<LoteRead[]>(`/emergencias/${emergenciaId}/lotes`)
}
