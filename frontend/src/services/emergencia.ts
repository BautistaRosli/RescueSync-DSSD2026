import { apiDelete, apiGet, apiPatch, apiPost } from './http'
import type {
  EvaluacionProyectoRead,
  EvaluacionProyectoRequest,
  EvaluacionProyectoAceptada,
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
  const { publicada, estado, etapa_bonita, pagina, por_pagina } = params
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
  if (etapa_bonita !== undefined) {
    consulta.set('etapa_bonita', etapa_bonita)
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


export async function obtenerEmergencia(emergenciaId: number): Promise<EmergenciaRead> {
  return apiGet<EmergenciaRead>(`/emergencias/${emergenciaId}`)
}

export async function obtenerEvaluacionProyecto(emergenciaId: number, incluirSeleccion = false): Promise<EvaluacionProyectoRead> {
  return apiGet<EvaluacionProyectoRead>(`/emergencias/${emergenciaId}/evaluacion-proyecto${incluirSeleccion ? '?incluir_seleccion=true' : ''}`)
}

export async function evaluarProyecto(
  emergenciaId: number,
  datos: EvaluacionProyectoRequest,
): Promise<EvaluacionProyectoAceptada> {
  return apiPost<EvaluacionProyectoAceptada>(`/emergencias/${emergenciaId}/evaluacion-proyecto`, datos)
}
