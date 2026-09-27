import { apiGet, apiPatch, apiPost } from './http'
import type {
  OfertaCreateRequest,
  OfertaRead,
  OfertaUpdateRequest,
  OfertasConsolidadas,
} from '../types'

export async function listarOfertasDeOrganizacion(
  organizacionId: number,
): Promise<OfertaRead[]> {
  return apiGet<OfertaRead[]>(`/ofertas?organizacion_id=${organizacionId}`)
}

export async function crearOferta(
  datos: OfertaCreateRequest,
): Promise<OfertaRead> {
  return apiPost<OfertaRead>('/ofertas', datos)
}

export async function actualizarOferta(
  ofertaId: number,
  datos: OfertaUpdateRequest,
): Promise<OfertaRead> {
  return apiPatch<OfertaRead>(`/ofertas/${ofertaId}`, datos)
}

export async function obtenerOfertasConsolidadas(
  emergenciaId: number,
): Promise<OfertasConsolidadas> {
  return apiGet<OfertasConsolidadas>(
    `/emergencias/${emergenciaId}/ofertas/consolidadas`,
  )
}
