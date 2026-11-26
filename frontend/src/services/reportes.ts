import { apiDescargar, apiGet } from './http'
import type { FiltrosReportes, FormatoReporte, Tablero } from '../types'

const dosDigitos = (valor: number) => String(valor).padStart(2, '0')

// Desplazamiento de la zona horaria del navegador (p. ej. "-03:00") vigente en esa fecha y hora local.
function desplazamientoZona(fecha: string, horas: number, minutos: number, segundos: number, milisegundos: number): string {
  const [anio, mes, dia] = fecha.split('-').map(Number)
  const diferencia = -new Date(anio, mes - 1, dia, horas, minutos, segundos, milisegundos).getTimezoneOffset()
  const absoluta = Math.abs(diferencia)
  return `${diferencia < 0 ? '-' : '+'}${dosDigitos(Math.floor(absoluta / 60))}:${dosDigitos(absoluta % 60)}`
}

function construirConsulta(filtros: FiltrosReportes = {}, formato?: FormatoReporte): string {
  const consulta = new URLSearchParams()
  if (filtros.desde) consulta.set('desde', `${filtros.desde}T00:00:00${desplazamientoZona(filtros.desde, 0, 0, 0, 0)}`)
  if (filtros.hasta) consulta.set('hasta', `${filtros.hasta}T23:59:59.999${desplazamientoZona(filtros.hasta, 23, 59, 59, 999)}`)
  if (filtros.nivel_gravedad) consulta.set('nivel_gravedad', filtros.nivel_gravedad)
  if (formato) consulta.set('formato', formato)
  const texto = consulta.toString()
  return texto ? `?${texto}` : ''
}

export function obtenerTablero(filtros: FiltrosReportes): Promise<Tablero> {
  return apiGet<Tablero>(`/reportes/tablero${construirConsulta(filtros)}`)
}

export function exportarReporteCompleto(filtros: FiltrosReportes, formato: FormatoReporte): Promise<Blob> {
  return apiDescargar(`/reportes/exportar${construirConsulta(filtros, formato)}`)
}
