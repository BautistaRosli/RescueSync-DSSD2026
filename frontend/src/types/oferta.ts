import type { OrganizacionResumen } from './organizacion'

export interface OfertaItemRead {
  id: number
  lote_necesidad_id: number
  cantidad_ofrecida: number
  descripcion: string | null
  finalizado_en: string | null
}

export interface OfertaItemRequest {
  lote_necesidad_id: number
  cantidad_ofrecida: number
  descripcion?: string | null
}

export interface OfertaRead {
  id: number
  emergencia_id: number
  organizacion_id: number
  observaciones: string | null
  fecha_hora_oferta: string
  es_conjunta: boolean
  organizaciones: OrganizacionResumen[]
  items: OfertaItemRead[]
}

export interface OfertaCreateRequest {
  emergencia_id: number
  organizacion_id: number
  observaciones?: string | null
  items: OfertaItemRequest[]
  organizaciones_ids: number[]
  es_conjunta: boolean
}

export interface OfertaUpdateRequest {
  observaciones?: string | null
  items?: OfertaItemRequest[]
  organizaciones_ids?: number[]
  es_conjunta?: boolean
}

export interface OfertaItemConsolidado {
  lote_id: number
  cantidad_ofrecida: number
  descripcion: string | null
}

export interface OfertaConsolidada {
  organizacion_id: number
  organizacion_nombre: string
  items: OfertaItemConsolidado[]
}

export interface OfertasConsolidadas {
  emergencia_id: number
  ofertas: OfertaConsolidada[]
}

export interface AdjudicacionRespuesta {
  oferta_id: number
  mensaje: string
}
