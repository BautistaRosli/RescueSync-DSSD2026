import { useState } from 'react'
import { Navbar } from './components'
import {
  CentroCoordinadorPage,
  EmergenciasPage,
  LoginPage,
  PanelOngPage,
  RegistroPage,
  RegistrarEmergenciaPage,
} from './pages'
import type { AuthResponse } from './types'
import { cerrarSesion } from './services'

type Vista = 'bandeja' | 'registro'

type VistaOperador = 'registrar' | 'emergencias'

const ROL_OPERADOR_MUNICIPAL = 'OPERADOR_MUNICIPAL'

const ROL_REPRESENTANTE_ONG = 'REPRESENTANTE_ONG'
const ROL_CENTRO_COORDINADOR = 'CENTRO_COORDINADOR'

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
  const [vista, setVista] = useState<Vista>('bandeja')
  const [vistaOperador, setVistaOperador] = useState<VistaOperador>('registrar')
  const [sesion, setSesion] = useState<AuthResponse | null>(null)

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <Navbar sesion={sesion} onCerrarSesion={() => {
        cerrarSesion()
        setSesion(null)
        setVista('bandeja')
      }} />

      <main className="mx-auto max-w-3xl px-4 py-8">
        {sesion === null ? (
          <LoginPage onSesionIniciada={setSesion} />
        ) : sesion.rol === ROL_OPERADOR_MUNICIPAL ? (
          <section className="flex flex-col gap-6">
            <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
              <h2 className="text-xl font-bold text-cyan-400 mb-1">
                Operador municipal
              </h2>
              <p className="text-sm text-slate-400">
                Registrá una emergencia del desastre o consultá las que están sin
                publicar.
              </p>
            </div>

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
              <RegistrarEmergenciaPage />
            ) : (
              <EmergenciasPage />
            )}
          </section>
        ) : sesion.rol === ROL_REPRESENTANTE_ONG ? (
          <PanelOngPage sesion={sesion} />
        ) : sesion.rol === ROL_CENTRO_COORDINADOR ? (
          vista === 'registro' ? (
            <RegistroPage onVolver={() => setVista('bandeja')} />
          ) : (
            <section className="flex flex-col gap-4">
              {/* <button type="button" onClick={() => setVista('registro')}
                className={clasePestania(false)}>
                Crear usuario
              </button> */}
              <CentroCoordinadorPage />
            </section>
          )
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
