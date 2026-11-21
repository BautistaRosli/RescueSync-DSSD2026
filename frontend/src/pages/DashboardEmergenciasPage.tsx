import { useEffect, useState } from 'react'
import { DashboardEmergencias, ReportesDashboard } from '../components'
import {
  ApiError,
  obtenerDashboardEmergencias,
  obtenerReporteCoberturaLotes,
  obtenerReporteConsorcios,
  obtenerReporteDemandaOferta,
  obtenerReporteEmergencias,
  obtenerReporteProyectos,
  obtenerReporteRankingOngs,
  obtenerReporteSuministrosMovilizados,
  obtenerReporteTiempoAdjudicacion,
  obtenerReporteTiempoPublicacion,
} from '../services'
import type { DatosReportesDashboard } from '../components'
import type { DashboardEmergencias as DashboardEmergenciasDatos } from '../types'

function describirError(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function DashboardEmergenciasPage() {
  const [datos, setDatos] = useState<DashboardEmergenciasDatos | null>(null)
  const [reportes, setReportes] = useState<DatosReportesDashboard>({ errores: [] })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      const resultados = await Promise.allSettled([
        obtenerDashboardEmergencias(),
        obtenerReporteEmergencias(),
        obtenerReporteSuministrosMovilizados(),
        obtenerReporteConsorcios(),
        obtenerReporteProyectos(),
        obtenerReporteCoberturaLotes(),
        obtenerReporteTiempoPublicacion(),
        obtenerReporteTiempoAdjudicacion(),
        obtenerReporteRankingOngs(),
        obtenerReporteDemandaOferta(),
      ])
      if (!vigente) return

      const [dashboard, emergencias, suministros, consorcios, proyectos, cobertura, tiempoPublicacion, tiempoAdjudicacion, rankingOngs, demandaOferta] = resultados
      if (dashboard.status === 'fulfilled') setDatos(dashboard.value)
      else setError(describirError(dashboard.reason))

      const datosReportes: DatosReportesDashboard = { errores: [] }
      const asignar = <T,>(resultado: PromiseSettledResult<T>, nombre: string, asignador: (valor: T) => void) => {
        if (resultado.status === 'fulfilled') asignador(resultado.value)
        else datosReportes.errores.push(`${nombre}: ${describirError(resultado.reason)}`)
      }
      asignar(emergencias, 'emergencias', (valor) => { datosReportes.emergencias = valor })
      asignar(suministros, 'suministros movilizados', (valor) => { datosReportes.suministros = valor })
      asignar(consorcios, 'consorcios', (valor) => { datosReportes.consorcios = valor })
      asignar(proyectos, 'proyectos', (valor) => { datosReportes.proyectos = valor })
      asignar(cobertura, 'cobertura de lotes', (valor) => { datosReportes.cobertura = valor })
      asignar(tiempoPublicacion, 'tiempo de publicación', (valor) => { datosReportes.tiempoPublicacion = valor })
      asignar(tiempoAdjudicacion, 'tiempo de adjudicación', (valor) => { datosReportes.tiempoAdjudicacion = valor })
      asignar(rankingOngs, 'ranking de ONG', (valor) => { datosReportes.rankingOngs = valor })
      asignar(demandaOferta, 'demanda y oferta', (valor) => { datosReportes.demandaOferta = valor })
      setReportes(datosReportes)
      setCargando(false)
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
      {!cargando && <ReportesDashboard datos={reportes} />}
    </section>
  )
}
