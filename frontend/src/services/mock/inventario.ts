// MOCK: reemplazar por llamadas a la API cuando exista el backend.
// Las firmas son async y equivalentes a las de un service real, así el cambio
// se limita al cuerpo de cada función.

import { clave, escribir, leer, proximoId } from './almacen'
import type { RecursoInventario, RecursoInventarioRequest } from '../../types'

function claveInventario(organizacionId: number): string {
  return clave('inventario', organizacionId)
}

export async function listarInventario(
  organizacionId: number,
): Promise<RecursoInventario[]> {
  return leer<RecursoInventario[]>(claveInventario(organizacionId), [])
}

export async function crearRecurso(
  organizacionId: number,
  datos: RecursoInventarioRequest,
): Promise<RecursoInventario> {
  const recursos = await listarInventario(organizacionId)
  const recurso: RecursoInventario = {
    id: proximoId(recursos),
    organizacion_id: organizacionId,
    tipo: datos.tipo,
    cantidad_total: datos.cantidad_total,
    unidad: datos.unidad ?? null,
    descripcion: datos.descripcion ?? null,
  }
  escribir(claveInventario(organizacionId), [...recursos, recurso])
  return recurso
}

export async function actualizarRecurso(
  organizacionId: number,
  recursoId: number,
  datos: RecursoInventarioRequest,
): Promise<RecursoInventario> {
  const recursos = await listarInventario(organizacionId)
  const actualizados = recursos.map((recurso) =>
    recurso.id === recursoId
      ? {
          ...recurso,
          tipo: datos.tipo,
          cantidad_total: datos.cantidad_total,
          unidad: datos.unidad ?? null,
          descripcion: datos.descripcion ?? null,
        }
      : recurso,
  )
  escribir(claveInventario(organizacionId), actualizados)
  const actualizado = actualizados.find((recurso) => recurso.id === recursoId)
  if (actualizado === undefined) {
    throw new Error('El recurso ya no existe en el inventario.')
  }
  return actualizado
}

export async function eliminarRecurso(
  organizacionId: number,
  recursoId: number,
): Promise<void> {
  const recursos = await listarInventario(organizacionId)
  escribir(
    claveInventario(organizacionId),
    recursos.filter((recurso) => recurso.id !== recursoId),
  )
}
