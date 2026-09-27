// MOCK: reemplazar por llamadas a la API cuando exista el backend.
// La adjudicación la hace el municipio (etapa 5 del flujo); hasta que ese
// módulo exista, las notificaciones se guardan y simulan localmente.

import { clave, escribir, leer, proximoId } from './almacen'
import type { NotificacionAdjudicacion } from '../../types'

function claveNotificaciones(organizacionId: number): string {
  return clave('notificaciones', organizacionId)
}

export async function listarNotificaciones(
  organizacionId: number,
): Promise<NotificacionAdjudicacion[]> {
  const notificaciones = leer<NotificacionAdjudicacion[]>(
    claveNotificaciones(organizacionId),
    [],
  )
  return [...notificaciones].sort((a, b) => b.id - a.id)
}

export async function marcarLeida(
  organizacionId: number,
  notificacionId: number,
): Promise<void> {
  const notificaciones = await listarNotificaciones(organizacionId)
  escribir(
    claveNotificaciones(organizacionId),
    notificaciones.map((notificacion) =>
      notificacion.id === notificacionId
        ? { ...notificacion, leida: true }
        : notificacion,
    ),
  )
}

/** Genera una notificación a partir de una oferta real, solo para la demo. */
export async function simularAdjudicacion(
  organizacionId: number,
  datos: {
    ofertaId: number
    emergenciaId: number
    zonaAfectada: string
    lotesAdjudicados: string[]
  },
): Promise<NotificacionAdjudicacion> {
  const notificaciones = await listarNotificaciones(organizacionId)
  const notificacion: NotificacionAdjudicacion = {
    id: proximoId(notificaciones),
    oferta_id: datos.ofertaId,
    emergencia_id: datos.emergenciaId,
    zona_afectada: datos.zonaAfectada,
    lotes_adjudicados: datos.lotesAdjudicados,
    fecha_hora: new Date().toISOString(),
    leida: false,
  }
  escribir(claveNotificaciones(organizacionId), [
    ...notificaciones,
    notificacion,
  ])
  return notificacion
}
