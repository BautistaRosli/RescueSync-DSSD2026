const API_BASE = 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const esObjeto = (valor: unknown): valor is Record<string, unknown> =>
  typeof valor === 'object' && valor !== null

const esCadena = (valor: unknown): valor is string => typeof valor === 'string'

function escribirDetalleValidacion(errores: Record<string, unknown>[]): string {
  return errores
    .map((error) => {
      const mensaje = esCadena(error.msg) ? error.msg : 'valor inválido'
      const ubicacion = Array.isArray(error.loc)
        ? error.loc.filter((parte) => esCadena(parte)).join('.')
        : ''
      return ubicacion ? `${ubicacion}: ${mensaje}` : mensaje
    })
    .join(' · ')
}

function escribirDetalle(cuerpo: unknown, status: number): string {
  if (esObjeto(cuerpo) && 'detail' in cuerpo) {
    const detalle = cuerpo.detail
    if (esCadena(detalle)) {
      return detalle
    }
    if (Array.isArray(detalle) && detalle.length > 0 && detalle.every(esObjeto)) {
      return escribirDetalleValidacion(detalle)
    }
  }
  if (status === 422) {
    return 'Los datos enviados no son válidos. Revisá los campos del formulario.'
  }
  if (status === 0) {
    return 'No se pudo conectar con el servidor. Verificá que el backend esté levantado.'
  }
  return `Error ${status} del servidor.`
}

async function apiPeticion<T>(
  ruta: string,
  metodo: 'GET' | 'POST',
  cuerpo?: unknown,
): Promise<T> {
  let respuesta: Response

  try {
    respuesta = await fetch(`${API_BASE}${ruta}`, {
      method: metodo,
      headers: { 'Content-Type': 'application/json' },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    })
  } catch {
    throw new ApiError(0, escribirDetalle(null, 0))
  }

  const cuerpoRespuesta: unknown = await respuesta.json().catch(() => null)

  if (!respuesta.ok) {
    throw new ApiError(respuesta.status, escribirDetalle(cuerpoRespuesta, respuesta.status))
  }

  if (cuerpoRespuesta === null) {
    throw new ApiError(respuesta.status, 'La respuesta del servidor no pudo interpretarse.')
  }

  return cuerpoRespuesta as T
}

export async function apiPost<T>(ruta: string, cuerpo: unknown): Promise<T> {
  return apiPeticion<T>(ruta, 'POST', cuerpo)
}
