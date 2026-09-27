// MOCK: reemplazar por llamadas a la API cuando exista el backend.
// Persistencia local en localStorage, acotada al navegador del usuario.

const PREFIJO = 'rescuesync'

export function clave(recurso: string, id: number | string): string {
  return `${PREFIJO}:${recurso}:${id}`
}

export function leer<T>(claveAlmacen: string, porDefecto: T): T {
  try {
    const crudo = window.localStorage.getItem(claveAlmacen)
    if (crudo === null) {
      return porDefecto
    }
    return JSON.parse(crudo) as T
  } catch {
    return porDefecto
  }
}

export function escribir<T>(claveAlmacen: string, valor: T): void {
  try {
    window.localStorage.setItem(claveAlmacen, JSON.stringify(valor))
  } catch {
    // El storage puede estar bloqueado (modo privado): se ignora.
  }
}

export function proximoId(elementos: { id: number }[]): number {
  return elementos.reduce((mayor, elemento) => Math.max(mayor, elemento.id), 0) + 1
}
