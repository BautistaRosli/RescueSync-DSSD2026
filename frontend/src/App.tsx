import { useState } from 'react'
import { LoginPage, RegistroPage, RegistrarEmergenciaPage } from './pages'
import type { AuthResponse } from './types'

type Vista = 'login' | 'registro'

const ROL_OPERADOR_MUNICIPAL = 'OPERADOR_MUNICIPAL'

function App() {
  const [vista, setVista] = useState<Vista>('login')
  const [sesion, setSesion] = useState<AuthResponse | null>(null)

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <header className="border-b border-slate-700 bg-slate-800/60">
        <div className="mx-auto max-w-md px-4 py-6">
          <h1 className="text-3xl font-bold tracking-tight text-cyan-400">
            RescueSync
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Coordinación de rescates en emergencias.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 py-8">
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
          <RegistrarEmergenciaPage
            sesion={sesion}
            onCerrarSesion={() => setSesion(null)}
          />
        ) : (
          <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
            <h2 className="text-xl font-bold text-amber-400 mb-1">
              Sección no disponible
            </h2>
            <p className="text-sm text-slate-400 mb-5">
              Esta sección es exclusiva para operadores municipales. Tu rol actual es{' '}
              <span className="font-mono text-cyan-400">{sesion.rol}</span>.
            </p>

            <button
              type="button"
              onClick={() => setSesion(null)}
              className="w-full rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
            >
              Cerrar sesión
            </button>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
