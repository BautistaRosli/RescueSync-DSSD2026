import { apiDelete, apiGet, apiPatch, apiPost } from './http'
import type {
  BandaEmergencias,
  BandaEmergenciasParams,
  DashboardEmergencias,
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

export async function obtenerDashboardEmergencias(): Promise<DashboardEmergencias> {
  return apiGet<DashboardEmergencias>('/emergencias/dashboard')
}

export async function listarBandejaEmergencias(
  params: BandaEmergenciasParams,
): Promise<BandaEmergencias> {
  const { publicada, estado, pagina, por_pagina } = params
  const consulta = new URLSearchParams({
    pagina: String(pagina),
    por_pagina: String(por_pagina),
  })
  if (publicada !== undefined) {
    consulta.set('publicada', String(publicada))
  }
  if (estado !== undefined) {
    consulta.set('estado', estado)
  }
  return apiGet<BandaEmergencias>(
    `/emergencias/bandeja?${consulta.toString()}`,
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
