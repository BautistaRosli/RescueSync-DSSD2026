import { ApiError } from '../services'
import type { EmergenciaRead, EstadoEmergencia, NivelGravedad } from '../types'

export const NIVELES_GRAVEDAD: { valor: NivelGravedad; etiqueta: string }[] = [
  { valor: 'baja', etiqueta: 'Baja' },
  { valor: 'media', etiqueta: 'Media' },
  { valor: 'alta', etiqueta: 'Alta' },
  { valor: 'critica', etiqueta: 'Crítica' },
]

export const ESTADOS_EMERGENCIA: { valor: EstadoEmergencia; etiqueta: string }[] =
  [
    { valor: 'esperando_lotes', etiqueta: 'Esperando lotes' },
    { valor: 'esperando_ofertas', etiqueta: 'Esperando ofertas' },
    { valor: 'en_proceso', etiqueta: 'En proceso' },
    { valor: 'resuelta', etiqueta: 'Resuelta' },
  ]

export function etiquetaDeGravedad(nivel: NivelGravedad): string {
  return NIVELES_GRAVEDAD.find((opcion) => opcion.valor === nivel)?.etiqueta ?? nivel
}

export function etiquetaDeEstado(estado: EstadoEmergencia | null): string {
  if (estado === null) {
    return 'Sin estado'
  }
  return ESTADOS_EMERGENCIA.find((opcion) => opcion.valor === estado)?.etiqueta ?? estado
}

export function formatearFecha(valor: string | null, sinDato: string): string {
  if (valor === null) {
    return sinDato
  }
  const fecha = new Date(valor)
  return Number.isNaN(fecha.getTime()) ? valor : fecha.toLocaleString('es-AR')
}

export function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

function fechaDeCierre(emergencia: EmergenciaRead): Date | null {
  const valor = emergencia.fecha_cierre_convocatoria
  if (valor === undefined || valor === null) {
    return null
  }
  const fecha = new Date(valor)
  return Number.isNaN(fecha.getTime()) ? null : fecha
}

/**
 * Indica si la ventana de convocatoria sigue abierta.
 *
 * Si la emergencia trae `fecha_cierre_convocatoria` (campo que suma otro
 * integrante del equipo) se compara contra la hora actual. Mientras ese campo
 * no exista, se usa el criterio disponible hoy: emergencia publicada y a la
 * espera de ofertas.
 */
export function convocatoriaAbierta(emergencia: EmergenciaRead): boolean {
  if (!emergencia.publicada) {
    return false
  }
  const cierre = fechaDeCierre(emergencia)
  if (cierre !== null) {
    return cierre.getTime() > Date.now()
  }
  return emergencia.estado === 'esperando_ofertas'
}

/** Texto del tiempo restante, o null si la emergencia no tiene fecha de cierre. */
export function tiempoRestante(emergencia: EmergenciaRead): string | null {
  const cierre = fechaDeCierre(emergencia)
  if (cierre === null) {
    return null
  }
  const milisegundos = cierre.getTime() - Date.now()
  if (milisegundos <= 0) {
    return 'Convocatoria cerrada'
  }
  const minutos = Math.floor(milisegundos / 60000)
  const dias = Math.floor(minutos / 1440)
  if (dias > 0) {
    return `Cierra en ${dias} día${dias === 1 ? '' : 's'}`
  }
  const horas = Math.floor(minutos / 60)
  if (horas > 0) {
    return `Cierra en ${horas} h`
  }
  return `Cierra en ${minutos} min`
}
