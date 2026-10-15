import type { AuthResponse } from '../types'

interface NavbarProps {
  sesion: AuthResponse | null
  onCerrarSesion: () => void
}

export function Navbar({ sesion, onCerrarSesion }: NavbarProps) {
  const nombreCompleto =
    sesion === null
      ? ''
      : [sesion.usuario.nombre, sesion.usuario.apellido]
          .filter(Boolean)
          .join(' ')

  return (
    <header className="border-b border-slate-700 bg-slate-800/60">
      <div className="mx-auto max-w-4xl px-4 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="RescueSync" className="h-16 w-auto" />
          <span className="bg-linear-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent text-2xl font-bold tracking-tight">
            RescueSync
          </span>
        </div>

        {sesion !== null && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-300">{nombreCompleto}</span>
            <span aria-hidden="true" className="h-4 w-px bg-slate-700" />
            <button
              type="button"
              onClick={onCerrarSesion}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
            >
              Cerrar sesión
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
