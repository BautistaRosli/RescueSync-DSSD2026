import { useEffect, useMemo, useState } from 'react'
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
  exportarReporteCompleto,
} from '../services'
import type {
  DashboardEmergencias as DashboardEmergenciasDatos,
  EmergenciaRead,
  FiltrosReportes,
  FormatoReporte,
} from '../types'

function filtrarEmergencia(emergencia: EmergenciaRead, filtros: FiltrosReportes): boolean {
  if (filtros.nivel_gravedad && emergencia.nivel_gravedad !== filtros.nivel_gravedad) return false
  const fecha = emergencia.fecha_hora_registro.slice(0, 10)
  if (filtros.desde && fecha < filtros.desde) return false
  if (filtros.hasta && fecha > filtros.hasta) return false
  return true
}

function describirError(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function DashboardEmergenciasPage() {
  const [datos, setDatos] = useState<DashboardEmergenciasDatos | null>(null)
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
        ])

        const emergenciasFiltradas = emergencias.filter((emergencia) => filtrarEmergencia(emergencia, filtros))
        const conteosPorEstado = emergenciasFiltradas.reduce<Record<string, number>>((conteos, emergencia) => {
          if (emergencia.estado !== null) {
            conteos[emergencia.estado] = (conteos[emergencia.estado] ?? 0) + 1
          }
          return conteos
        }, {})

        const resultado: DashboardEmergenciasDatos = {
          total: emergenciasFiltradas.length,
          conteos_por_estado: conteosPorEstado,
          emergencias: emergenciasFiltradas,
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
        <p className="mt-1 text-sm text-slate-400">
          Resumen general de las emergencias registradas.
        </p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm text-slate-300">
            Desde
            <input type="date" value={desde} onChange={(evento) => setDesde(evento.target.value)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-300">
            Hasta
            <input type="date" value={hasta} onChange={(evento) => setHasta(evento.target.value)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-300">
            Nivel de gravedad
            <select value={nivelGravedad ?? ''} onChange={(evento) => setNivelGravedad(evento.target.value ? evento.target.value as FiltrosReportes['nivel_gravedad'] : undefined)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white">
              <option value="">Todas</option>
              <option value="baja">Baja</option>
              <option value="media">Media</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
          </label>
        </div>
        <div className="mt-4 border-t border-slate-700 pt-4">
          <p className="mb-2 text-sm font-semibold text-slate-300">Exportar reporte filtrado</p>
          <p className="mb-3 text-xs text-slate-400">Descargá todas las métricas del dashboard usando los filtros seleccionados.</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select value={formatoExportar} onChange={(evento) => setFormatoExportar(evento.target.value as FormatoReporte)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white">
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
            <button type="button" onClick={() => void descargarReporte()} disabled={exportando} className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50">
              {exportando ? 'Exportando...' : 'Descargar reporte completo'}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">Las métricas de ejecución de Bonita requieren un endpoint agregado que todavía no está disponible.</p>
        </div>
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
