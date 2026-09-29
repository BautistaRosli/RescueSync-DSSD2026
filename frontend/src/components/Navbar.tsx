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
      <div className="mx-auto max-w-3xl px-4 py-6 flex flex-wrap items-center justify-between gap-4">
        <img src="/logo.png" alt="RescueSync" className="h-12 w-auto" />

        {sesion !== null && (
          <section
            aria-label="Sesión activa"
            className="flex min-w-56 flex-col gap-3 rounded-xl bg-slate-900 border border-slate-700 p-4 shadow-2xl"
          >
            <dl className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-xs text-slate-400">Usuario</dt>
                <dd className="text-sm font-semibold text-white">{nombreCompleto}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-xs text-slate-400">Rol</dt>
                <dd className="font-mono text-cyan-400">{sesion.rol}</dd>
              </div>
            </dl>

            <button
              type="button"
              onClick={onCerrarSesion}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
            >
              Cerrar sesión
            </button>
          </section>
        )}
      </div>
    </header>
  )
}
