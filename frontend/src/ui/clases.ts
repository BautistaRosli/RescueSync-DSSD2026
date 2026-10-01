// Clases de Tailwind compartidas por las pantallas del representante de ONG.
// Los valores se toman tal cual de las páginas existentes (RegistroPage,
// RegistrarEmergenciaPage, EmergenciasPage y App) para mantener un único
// look & feel en toda la aplicación.

export const claseCard =
  'rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl'

export const claseSubPanel =
  'rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm'

export const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60'

export const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

export const claseError =
  'rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300'

export const claseAviso =
  'rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm text-amber-300'

export const claseExito =
  'rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300'

export const claseBotonPrimario =
  'rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50'

export const claseBotonSecundario =
  'rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50'

export const claseBadge =
  'rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300'

export const claseBadgeAcento =
  'rounded-full border border-cyan-500/50 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-300'

export const claseBadgeExito =
  'rounded-full border border-emerald-500/50 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300'

export const claseBadgeAviso =
  'rounded-full border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300'

export const claseTitulo = 'text-xl font-bold text-cyan-400 mb-1'

export const claseSubtitulo = 'text-sm text-slate-400'

export function clasePestania(activa: boolean): string {
  return activa
    ? 'rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-900'
    : 'rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400'
}
