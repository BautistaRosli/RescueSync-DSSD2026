import { useEffect, useMemo, useState } from 'react'
import { DashboardEmergencias, ReportesDashboard } from '../components'
import type { DatosReportesDashboard } from '../components'
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
  exportarReporteCompleto,
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
import type {
  DashboardEmergencias as DashboardEmergenciasDatos,
  EmergenciaRead,
  FiltrosReportes,
  FormatoReporte,
  ReporteCoberturaLotes,
  ReporteConsorcios,
  ReporteDemandaOferta,
  ReporteEmergenciaGravedad,
  ReporteProyecto,
  ReporteRankingOng,
  ReporteSuministroMovilizado,
  ReporteTiempoAdjudicacion,
  ReporteTiempoPublicacion,
} from '../types'

function describirError(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Ocurrió un error inesperado. Intentá de nuevo.'
}

function filtrarEmergencia(emergencia: EmergenciaRead, filtros: FiltrosReportes): boolean {
  if (filtros.nivel_gravedad && emergencia.nivel_gravedad !== filtros.nivel_gravedad) return false
  const fecha = emergencia.fecha_hora_registro.slice(0, 10)
  if (filtros.desde && fecha < filtros.desde) return false
  if (filtros.hasta && fecha > filtros.hasta) return false
  return true
}

export function DashboardEmergenciasPage() {
  const [datos, setDatos] = useState<DashboardEmergenciasDatos | null>(null)
  const [reportes, setReportes] = useState<DatosReportesDashboard>({ errores: [] })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [nivelGravedad, setNivelGravedad] = useState<FiltrosReportes['nivel_gravedad']>()
  const [formatoExportar, setFormatoExportar] = useState<FormatoReporte>('csv')
  const [exportando, setExportando] = useState(false)

  const filtros: FiltrosReportes = useMemo(() => ({
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
    ...(nivelGravedad ? { nivel_gravedad: nivelGravedad } : {}),
  }), [desde, hasta, nivelGravedad])

  useEffect(() => {
    let vigente = true

    async function cargar() {
      await Promise.resolve()
      if (!vigente) return
      setCargando(true)
      setError(null)
      const resultados = await Promise.allSettled([
        listarEmergencias(),
        obtenerEmergenciasPorEstadoYGravedad(filtros),
        obtenerActivasResueltas(filtros),
        obtenerEvolucionAbiertasResueltas(filtros),
        obtenerNecesidadesActuales(filtros),
        obtenerSuministrosMovilizados(filtros),
        obtenerParticipacionConsorcios(filtros),
        obtenerDemandaOferta(filtros),
        obtenerRankingOngs(filtros),
        obtenerTiempoVida(filtros),
        obtenerPrioridadAbiertas(filtros),
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

      const datosReportes: DatosReportesDashboard = { errores: [] }
      const asignarReporte = <T,>(indice: number, nombre: string, asignador: (valor: T) => void) => {
        const resultado = resultados[indice]
        if (resultado.status === 'fulfilled') asignador(resultado.value as T)
        else datosReportes.errores.push(`${nombre}: ${describirError(resultado.reason)}`)
      }
      asignarReporte<ReporteEmergenciaGravedad[]>(11, 'emergencias', (valor) => { datosReportes.emergencias = valor })
      asignarReporte<ReporteSuministroMovilizado[]>(12, 'suministros movilizados', (valor) => { datosReportes.suministros = valor })
      asignarReporte<ReporteConsorcios>(13, 'consorcios', (valor) => { datosReportes.consorcios = valor })
      asignarReporte<ReporteProyecto[]>(14, 'proyectos', (valor) => { datosReportes.proyectos = valor })
      asignarReporte<ReporteCoberturaLotes>(15, 'cobertura de lotes', (valor) => { datosReportes.cobertura = valor })
      asignarReporte<ReporteTiempoPublicacion>(16, 'tiempo de publicación', (valor) => { datosReportes.tiempoPublicacion = valor })
      asignarReporte<ReporteTiempoAdjudicacion>(17, 'tiempo de adjudicación', (valor) => { datosReportes.tiempoAdjudicacion = valor })
      asignarReporte<ReporteRankingOng[]>(18, 'ranking de ONG', (valor) => { datosReportes.rankingOngs = valor })
      asignarReporte<ReporteDemandaOferta[]>(19, 'demanda y oferta', (valor) => { datosReportes.demandaOferta = valor })
      setReportes(datosReportes)

      const resultadoEmergencias = resultados[0]
      const metricas = resultados.slice(1, 11)
      const falloPrincipal = [resultadoEmergencias, ...metricas].find((resultado) => resultado.status === 'rejected')
      if (falloPrincipal?.status === 'rejected') {
        setError(describirError(falloPrincipal.reason))
      } else {
        const emergencias = (resultadoEmergencias as PromiseFulfilledResult<EmergenciaRead[]>).value
          .filter((emergencia) => filtrarEmergencia(emergencia, filtros))
        const emergenciasPorEstadoYGravedad = (metricas[0] as PromiseFulfilledResult<DashboardEmergenciasDatos['emergencias_por_estado_y_gravedad']>).value
        const activasResueltas = (metricas[1] as PromiseFulfilledResult<Awaited<ReturnType<typeof obtenerActivasResueltas>>>).value
        const evolucion = (metricas[2] as PromiseFulfilledResult<DashboardEmergenciasDatos['evolucion_abiertas_resueltas']>).value
        const necesidades = (metricas[3] as PromiseFulfilledResult<DashboardEmergenciasDatos['necesidades_actuales']>).value
        const suministros = (metricas[4] as PromiseFulfilledResult<DashboardEmergenciasDatos['recursos_adjudicados_por_mes']>).value
        const consorcios = (metricas[5] as PromiseFulfilledResult<DashboardEmergenciasDatos['participacion_consorcios']>).value
        const demandaOferta = (metricas[6] as PromiseFulfilledResult<DashboardEmergenciasDatos['demanda_vs_oferta_por_recurso']>).value
        const rankingOngs = (metricas[7] as PromiseFulfilledResult<DashboardEmergenciasDatos['ranking_ongs']>).value
        const tiempoVida = (metricas[8] as PromiseFulfilledResult<{ promedio_horas: number }>).value
        const prioridadAbiertas = (metricas[9] as PromiseFulfilledResult<{ promedio_prioridad: number; cantidad_emergencias: number }>).value
        const conteosPorEstado = emergencias.reduce<Record<string, number>>((conteos, emergencia) => {
          if (emergencia.estado !== null) conteos[emergencia.estado] = (conteos[emergencia.estado] ?? 0) + 1
          return conteos
        }, {})
        setDatos({
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
        })
      }
      setCargando(false)
    }

    void cargar().catch((fallo: unknown) => {
      if (vigente) {
        setError(describirError(fallo))
        setCargando(false)
      }
    })
    return () => { vigente = false }
  }, [filtros])

  async function descargarReporte() {
    setExportando(true)
    try {
      const archivo = await exportarReporteCompleto(filtros, formatoExportar)
      const url = URL.createObjectURL(archivo)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `reporte-completo.${formatoExportar}`
      enlace.click()
      URL.revokeObjectURL(url)
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setExportando(false)
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400">Dashboard de emergencias</h2>
        <p className="mt-1 text-sm text-slate-400">Resumen general de las emergencias registradas.</p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm text-slate-300">Desde<input type="date" value={desde} onChange={(evento) => setDesde(evento.target.value)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" /></label>
          <label className="flex flex-col gap-1 text-sm text-slate-300">Hasta<input type="date" value={hasta} onChange={(evento) => setHasta(evento.target.value)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" /></label>
          <label className="flex flex-col gap-1 text-sm text-slate-300">Nivel de gravedad<select value={nivelGravedad ?? ''} onChange={(evento) => setNivelGravedad(evento.target.value ? evento.target.value as FiltrosReportes['nivel_gravedad'] : undefined)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white"><option value="">Todas</option><option value="baja">Baja</option><option value="media">Media</option><option value="alta">Alta</option><option value="critica">Crítica</option></select></label>
        </div>
        <div className="mt-4 border-t border-slate-700 pt-4">
          <p className="mb-2 text-sm font-semibold text-slate-300">Exportar reporte filtrado</p>
          <p className="mb-3 text-xs text-slate-400">Descargá todas las métricas del dashboard usando los filtros seleccionados.</p>
          <div className="flex flex-col gap-2 sm:flex-row"><select value={formatoExportar} onChange={(evento) => setFormatoExportar(evento.target.value as FormatoReporte)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white"><option value="csv">CSV</option><option value="json">JSON</option></select><button type="button" onClick={() => void descargarReporte()} disabled={exportando} className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50">{exportando ? 'Exportando...' : 'Descargar reporte completo'}</button></div>
          <p className="mt-3 text-xs text-slate-500">Las métricas de ejecución de Bonita requieren un endpoint agregado que todavía no está disponible.</p>
        </div>
      </div>
      {cargando && <p className="rounded-xl border border-slate-700 bg-slate-800 p-6 text-sm text-slate-400">Cargando dashboard...</p>}
      {!cargando && error !== null && <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">No se pudo cargar el dashboard. {error}</p>}
      {!cargando && error === null && datos !== null && <DashboardEmergencias datos={datos} />}
      {!cargando && <ReportesDashboard datos={reportes} />}
    </section>
  )
}
