import { useState } from 'react'
import {
  EmergenciasPage,
  LoginPage,
  PanelOngPage,
  RegistroPage,
  RegistrarEmergenciaPage,
} from './pages'
import type { AuthResponse } from './types'

type Vista = 'login' | 'registro'

type VistaOperador = 'registrar' | 'emergencias'

const ROL_OPERADOR_MUNICIPAL = 'OPERADOR_MUNICIPAL'

const ROL_REPRESENTANTE_ONG = 'REPRESENTANTE_ONG'

const PESTANIAS_OPERADOR: { valor: VistaOperador; etiqueta: string }[] = [
  { valor: 'registrar', etiqueta: 'Registrar emergencia' },
  { valor: 'emergencias', etiqueta: 'Emergencias' },
]

function clasePestania(activa: boolean): string {
  return activa
    ? 'rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-900'
    : 'rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400'
}

function App() {
  const [vista, setVista] = useState<Vista>('login')
  const [vistaOperador, setVistaOperador] = useState<VistaOperador>('registrar')
  const [sesion, setSesion] = useState<AuthResponse | null>(null)

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <header className="border-b border-slate-700 bg-slate-800/60">
        <div className="mx-auto max-w-3xl px-4 py-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-cyan-400">
              RescueSync
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Coordinación de rescates en emergencias.
            </p>
          </div>

          {sesion !== null && (
            <div className="flex flex-col items-end gap-2">
              <p className="text-sm text-slate-300">
                {[sesion.usuario.nombre, sesion.usuario.apellido]
                  .filter(Boolean)
                  .join(' ')}
              </p>
              <button
                type="button"
                onClick={() => setSesion(null)}
                className="rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
              >
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        {sesion === null ? (
          vista === 'login' ? (
            <LoginPage
              onIrARegistro={() => setVista('registro')}
              onSesionIniciada={setSesion}
            />
          ) : (
            <RegistroPage onIrALogin={() => setVista('login')} />
          )
        ) : sesion.rol === ROL_OPERADOR_MUNICIPAL ? (
          <section className="flex flex-col gap-6">
            <nav
              aria-label="Secciones del operador"
              className="flex flex-wrap gap-2"
            >
              {PESTANIAS_OPERADOR.map((pestania) => (
                <button
                  key={pestania.valor}
                  type="button"
                  aria-current={vistaOperador === pestania.valor ? 'page' : undefined}
                  onClick={() => setVistaOperador(pestania.valor)}
                  className={clasePestania(vistaOperador === pestania.valor)}
                >
                  {pestania.etiqueta}
                </button>
              ))}
            </nav>

            {vistaOperador === 'registrar' ? (
              <RegistrarEmergenciaPage sesion={sesion} />
            ) : (
              <EmergenciasPage />
            )}
          </section>
        ) : sesion.rol === ROL_REPRESENTANTE_ONG ? (
          <PanelOngPage sesion={sesion} />
        ) : (
          <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
            <h2 className="text-xl font-bold text-amber-400 mb-1">
              Sección no disponible
            </h2>
            <p className="text-sm text-slate-400">
              Todavía no hay una sección para tu rol. Tu rol actual es{' '}
              <span className="font-mono text-cyan-400">{sesion.rol}</span>.
            </p>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
