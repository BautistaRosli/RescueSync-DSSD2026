import { apiDelete, apiGet, apiPatch, apiPost } from './http'
import type { RecursoInventario, RecursoInventarioRequest } from '../types'

export async function listarInventario(
  organizacionId: number,
): Promise<RecursoInventario[]> {
  return apiGet<RecursoInventario[]>(
    `/organizaciones/${organizacionId}/inventario`,
  )
}

export async function crearRecurso(
  organizacionId: number,
  datos: RecursoInventarioRequest,
): Promise<RecursoInventario> {
  return apiPost<RecursoInventario>(
    `/organizaciones/${organizacionId}/inventario`,
    datos,
  )
}

export async function actualizarRecurso(
  organizacionId: number,
  recursoId: number,
  datos: RecursoInventarioRequest,
): Promise<RecursoInventario> {
  return apiPatch<RecursoInventario>(
    `/organizaciones/${organizacionId}/inventario/${recursoId}`,
    datos,
  )
}

export async function eliminarRecurso(
  organizacionId: number,
  recursoId: number,
): Promise<void> {
  return apiDelete(`/organizaciones/${organizacionId}/inventario/${recursoId}`)
}
