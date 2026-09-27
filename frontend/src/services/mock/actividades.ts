// MOCK: reemplazar por llamadas a la API cuando exista el backend.
// Etapa 7 del flujo: la ONG marca sus actividades como finalizadas y la
// plataforma informa el cierre al sistema centralizado.

import { clave, escribir, leer } from './almacen'
import type { ActividadFinalizada } from '../../types'

function claveActividades(ofertaId: number): string {
  return clave('actividades', ofertaId)
}

export async function listarActividades(
  ofertaId: number,
): Promise<ActividadFinalizada[]> {
  return leer<ActividadFinalizada[]>(claveActividades(ofertaId), [])
}

export async function marcarFinalizada(
  ofertaId: number,
  loteNecesidadId: number,
): Promise<ActividadFinalizada> {
  const actividades = await listarActividades(ofertaId)
  const yaFinalizada = actividades.find(
    (actividad) => actividad.lote_necesidad_id === loteNecesidadId,
  )
  if (yaFinalizada !== undefined) {
    return yaFinalizada
  }
  const actividad: ActividadFinalizada = {
    lote_necesidad_id: loteNecesidadId,
    fecha_hora: new Date().toISOString(),
  }
  escribir(claveActividades(ofertaId), [...actividades, actividad])
  return actividad
}
