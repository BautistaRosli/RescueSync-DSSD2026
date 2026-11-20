import { useEffect, useState } from 'react'
import { DashboardEmergencias } from '../components'
import { ApiError, obtenerDashboardEmergencias } from '../services'
import type { DashboardEmergencias as DashboardEmergenciasDatos } from '../types'

function describirError(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function DashboardEmergenciasPage() {
  const [datos, setDatos] = useState<DashboardEmergenciasDatos | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const resultado = await obtenerDashboardEmergencias()
        if (vigente) {
          setDatos(resultado)
        }
      } catch (fallo) {
        if (vigente) {
          setError(describirError(fallo))
        }
      } finally {
        if (vigente) {
          setCargando(false)
        }
      }
    }

    void cargar()
    return () => {
      vigente = false
    }
  }, [])

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400">Dashboard de emergencias</h2>
        <p className="mt-1 text-sm text-slate-400">
          Resumen general de las emergencias registradas.
        </p>
      </div>
      {cargando && (
        <p className="rounded-xl border border-slate-700 bg-slate-800 p-6 text-sm text-slate-400">
          Cargando dashboard...
        </p>
      )}
      {!cargando && error !== null && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          No se pudo cargar el dashboard. {error}
        </p>
      )}
      {!cargando && error === null && datos !== null && <DashboardEmergencias datos={datos} />}
    </section>
  )
}
