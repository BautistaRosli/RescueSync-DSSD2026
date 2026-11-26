import type { OfertaCoordinadorRead } from '../types/oferta'

export function estaAdjudicadaParaCierre(oferta: OfertaCoordinadorRead): boolean {
  return oferta.estado_seleccion === 'adjudicada' ||
    (oferta.estado_seleccion == null && oferta.adjudicada_en != null)
}

export function puedeCerrarOferta(oferta: OfertaCoordinadorRead, ofertas: OfertaCoordinadorRead[]): boolean {
  return estaAdjudicadaParaCierre(oferta) && ofertas
    .filter((registro) => registro.emergencia_id === oferta.emergencia_id && estaAdjudicadaParaCierre(registro))
    .every((registro) => registro.items.length > 0 && registro.items.every((item) => item.finalizado_en != null))
}
