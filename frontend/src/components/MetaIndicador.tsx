import type { Indicador } from '../types'
import { etiquetaDeFuente } from '../utils/formato'

/** Línea "Qué mide · Fuente" de un indicador del tablero, con la marca "Global" si no respeta los filtros. */
export function MetaIndicador({ indicador }: { indicador: Indicador }) {
  return (
    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <span>Qué mide: {indicador.descripcion} · Fuente: {etiquetaDeFuente(indicador.fuente)}</span>
      {indicador.alcance === 'global' && (
        <span className="rounded-full border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-amber-300">Global</span>
      )}
    </p>
  )
}
