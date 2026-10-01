import { apiGet, apiPatch, apiPost } from './http'
import type {
  AdjudicacionRespuesta,
  OfertaCreateRequest,
  OfertaItemRead,
  OfertaRead,
  OfertaUpdateRequest,
  OfertasConsolidadas,
} from '../types'

export async function listarOfertasDeOrganizacion(
  organizacionId: number,
): Promise<OfertaRead[]> {
  return apiGet<OfertaRead[]>(`/ofertas?organizacion_id=${organizacionId}`)
}

export async function listarOfertasDeEmergencia(
  emergenciaId: number,
): Promise<OfertaRead[]> {
  return apiGet<OfertaRead[]>(`/ofertas?emergencia_id=${emergenciaId}`)
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

// El endpoint de adjudicación no declara cuerpo (solo usa el id de la ruta),
// pero apiPost exige el parámetro cuerpo, así que le mandamos un objeto vacío
// que FastAPI ignora.
export async function adjudicarOferta(
  ofertaId: number,
): Promise<AdjudicacionRespuesta> {
  return apiPost<AdjudicacionRespuesta>(`/ofertas/${ofertaId}/adjudicar`, {})
}

// Finalizar una actividad tampoco declara cuerpo (los ids viajan en la ruta),
// así que se le pasa un objeto vacío para cumplir con la firma de apiPost.
// Es idempotente: repetir la llamada devuelve el ítem con la misma fecha.
export async function finalizarItemOferta(
  ofertaId: number,
  itemId: number,
): Promise<OfertaItemRead> {
  return apiPost<OfertaItemRead>(
    `/ofertas/${ofertaId}/items/${itemId}/finalizar`,
    {},
  )
}
