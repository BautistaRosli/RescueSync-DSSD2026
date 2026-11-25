import type { OrganizacionResumen } from './organizacion'

export interface OfertaItemRead {
  id: number
  lote_necesidad_id: number
  cantidad_ofrecida: number
  descripcion: string | null
  finalizado_en: string | null
  aportes?: AporteOferta[]
}

export interface AporteOferta {
  organizacion_id: number
  cantidad: number
}

export interface OfertaItemRequest {
  lote_necesidad_id: number
  cantidad_ofrecida: number
  descripcion?: string | null
  aportes?: AporteOferta[]
}

export interface OfertaRead {
  id: number
  emergencia_id: number
  organizacion_id: number
  observaciones: string | null
  fecha_hora_oferta: string
  es_conjunta: boolean
  adjudicada_en: string | null
  organizaciones: OrganizacionResumen[]
  items: OfertaItemRead[]
}

export interface OfertaCoordinadorRead extends OfertaRead {
  puede_seleccionar: boolean
  estado_seleccion: 'sin_seleccionar' | 'seleccionada_para_confirmar' | 'adjudicada'
  items: (OfertaItemRead & { cantidad_verificada: number | null })[]
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

export interface FinalizarOfertaRespuesta {
  oferta_id: number
  estado: 'finalizada'
  ya_finalizada?: boolean
  mensaje: string
}

export interface SeleccionOfertasRespuesta {
  emergencia_id: number
  cantidad_pares: number
  ya_confirmada: boolean
}
