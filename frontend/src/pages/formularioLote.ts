import type { LoteNecesidad } from '../types'

export interface BorradorLote {
  tipo: string
  cantidad: string
  unidad: string
  descripcion: string
  tipo_recurso_id: string
}

export const BORRADOR_VACIO: BorradorLote = {
  tipo: '',
  cantidad: '',
  unidad: '',
  descripcion: '',
  tipo_recurso_id: '',
}

interface DatosLote {
  tipo: string
  cantidad: number
  unidad: string | null
  descripcion: string | null
  tipo_recurso_id: number
}

type ValidacionBorrador =
  | { error: string; datos: null }
  | { error: null; datos: DatosLote }

export function validarBorradorLote(borrador: BorradorLote): ValidacionBorrador {
  const tipo = borrador.tipo.trim()
  const cantidad = Number(borrador.cantidad)
  const tipoRecursoId = Number(borrador.tipo_recurso_id)

  if (!tipo) {
    return { error: 'Ingresá el tipo de lote.', datos: null }
  }
  if (!Number.isInteger(cantidad) || cantidad <= 0) {
    return { error: 'La cantidad debe ser un número entero mayor a 0.', datos: null }
  }
  if (!Number.isSafeInteger(tipoRecursoId) || tipoRecursoId <= 0) {
    return { error: 'Seleccioná un recurso del catálogo nacional antes de continuar.', datos: null }
  }
  return {
    error: null,
    datos: {
      tipo,
      cantidad,
      unidad: borrador.unidad.trim() || null,
      descripcion: borrador.descripcion.trim() || null,
      tipo_recurso_id: tipoRecursoId,
    },
  }
}

export function borradorDesdeLote(lote: LoteNecesidad): BorradorLote {
  return {
    tipo: lote.tipo,
    cantidad: String(lote.cantidad),
    unidad: lote.unidad ?? '',
    descripcion: lote.descripcion ?? '',
    tipo_recurso_id:
      lote.tipo_recurso_id !== null &&
      Number.isSafeInteger(lote.tipo_recurso_id) &&
      lote.tipo_recurso_id > 0
        ? String(lote.tipo_recurso_id)
        : '',
  }
}

export function cambiarCampoBorradorLote(
  borrador: BorradorLote,
  campo: keyof BorradorLote,
  valor: string,
): BorradorLote {
  const cambioDeRecurso = campo === 'tipo' && valor.trim() !== borrador.tipo.trim()
  return {
    ...borrador,
    [campo]: valor,
    ...(cambioDeRecurso ? { tipo_recurso_id: '' } : {}),
  }
}
