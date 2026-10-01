import { apiDelete, apiGet, apiPatch, apiPost } from './http'
import type {
  BandaEmergencias,
  BandaEmergenciasParams,
  EmergenciaCreateRequest,
  EmergenciaCreada,
  EmergenciaRead,
  LoteNecesidad,
  LoteNecesidadCreateRequest,
  LoteNecesidadUpdateRequest,
} from '../types'

export async function registrarEmergencia(
  datos: EmergenciaCreateRequest,
): Promise<EmergenciaCreada> {
  return apiPost<EmergenciaCreada>('/emergencias', datos)
}

export async function listarEmergencias(): Promise<EmergenciaRead[]> {
  return apiGet<EmergenciaRead[]>('/emergencias')
}

export async function listarBandejaEmergencias(
  params: BandaEmergenciasParams,
): Promise<BandaEmergencias> {
  const { publicada, pagina, por_pagina } = params
  return apiGet<BandaEmergencias>(
    `/emergencias/bandeja?publicada=${publicada}&pagina=${pagina}&por_pagina=${por_pagina}`,
  )
}

export async function crearLote(
  emergenciaId: number,
  datos: LoteNecesidadCreateRequest,
): Promise<LoteNecesidad> {
  return apiPost<LoteNecesidad>(`/emergencias/${emergenciaId}/lotes`, datos)
}

export async function publicarEmergencia(
  emergenciaId: number,
): Promise<EmergenciaRead> {
  return apiPost<EmergenciaRead>(`/emergencias/${emergenciaId}/publicar`, undefined)
}

export async function actualizarLote(
  loteId: number,
  datos: LoteNecesidadUpdateRequest,
): Promise<LoteNecesidad> {
  return apiPatch<LoteNecesidad>(`/lotes/${loteId}`, datos)
}

export async function eliminarLote(loteId: number): Promise<void> {
  return apiDelete(`/lotes/${loteId}`)
}
