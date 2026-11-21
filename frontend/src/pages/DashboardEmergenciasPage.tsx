import { useEffect, useState } from 'react'
import { DashboardEmergencias } from '../components'
import {
  ApiError,
  listarEmergencias,
  obtenerActivasResueltas,
  obtenerDemandaOferta,
  obtenerEmergenciasPorEstadoYGravedad,
  obtenerEvolucionAbiertasResueltas,
  obtenerNecesidadesActuales,
  obtenerParticipacionConsorcios,
  obtenerPrioridadAbiertas,
  obtenerRankingOngs,
  obtenerSuministrosMovilizados,
  obtenerTiempoVida,
} from '../services'
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
        const [
          emergencias,
          emergenciasPorEstadoYGravedad,
          activasResueltas,
          evolucion,
          necesidades,
          suministros,
          consorcios,
          demandaOferta,
          rankingOngs,
          tiempoVida,
          prioridadAbiertas,
        ] = await Promise.all([
          listarEmergencias(),
          obtenerEmergenciasPorEstadoYGravedad(),
          obtenerActivasResueltas(),
          obtenerEvolucionAbiertasResueltas(),
          obtenerNecesidadesActuales(),
          obtenerSuministrosMovilizados(),
          obtenerParticipacionConsorcios(),
          obtenerDemandaOferta(),
          obtenerRankingOngs(),
          obtenerTiempoVida(),
          obtenerPrioridadAbiertas(),
        ])

        const conteosPorEstado = emergencias.reduce<Record<string, number>>((conteos, emergencia) => {
          if (emergencia.estado !== null) {
            conteos[emergencia.estado] = (conteos[emergencia.estado] ?? 0) + 1
          }
          return conteos
        }, {})

        const resultado: DashboardEmergenciasDatos = {
          total: emergencias.length,
          conteos_por_estado: conteosPorEstado,
          emergencias,
          emergencias_activas: activasResueltas.activas,
          emergencias_resueltas: activasResueltas.resueltas,
          evolucion_abiertas_resueltas: evolucion,
          ranking_ongs: rankingOngs,
          cantidad_total_necesidades: necesidades.reduce((total, necesidad) => total + necesidad.cantidad_requerida, 0),
          tiempo_medio_vida_horas: tiempoVida.promedio_horas,
          participacion_consorcios: consorcios,
          recursos_adjudicados_por_mes: suministros,
          demanda_vs_oferta_por_recurso: demandaOferta,
          emergencias_por_estado_y_gravedad: emergenciasPorEstadoYGravedad,
          necesidades_actuales: necesidades,
          prioridad_abiertas: prioridadAbiertas,
        }
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
