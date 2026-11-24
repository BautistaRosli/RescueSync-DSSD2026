import { apiGet, apiPatch, apiPost } from './http'
import type { OfertaCoordinadorRead } from '../types/oferta'
import type {
  AdjudicacionRespuesta,
  OfertaCreateRequest,
  OfertaItemRead,
  OfertaRead,
  OfertaUpdateRequest,
  OfertasConsolidadas,
  SeleccionOfertasRespuesta,
} from '../types'

export async function listarOfertasDeOrganizacion(
  organizacionId: number,
): Promise<OfertaRead[]> {
  void organizacionId
  return apiGet<OfertaRead[]>('/ofertas')
}

export async function listarOfertasDeEmergencia(
  emergenciaId: number,
): Promise<OfertaCoordinadorRead[]> {
  return apiGet<OfertaCoordinadorRead[]>(`/emergencias/${emergenciaId}/ofertas`)
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

export async function adjudicarOferta(
  ofertaId: number,
  paraSeleccion = false,
): Promise<AdjudicacionRespuesta> {
  return apiPost<AdjudicacionRespuesta>(
    `/ofertas/${ofertaId}/adjudicar${paraSeleccion ? '?para_seleccion=true' : ''}`,
    undefined,
  )
}

export async function confirmarSeleccionOfertas(
  emergenciaId: number,
): Promise<SeleccionOfertasRespuesta> {
  return apiPost<SeleccionOfertasRespuesta>(
    `/emergencias/${emergenciaId}/confirmar-seleccion`,
    undefined,
  )
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
