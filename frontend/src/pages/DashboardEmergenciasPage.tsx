import { useEffect, useMemo, useState } from 'react'
import { DashboardEmergencias, ReportesDashboard } from '../components'
import { exportarReporteCompleto, obtenerTablero } from '../services'
import type { FiltrosReportes, FormatoReporte, Tablero } from '../types'
import { describirError, NIVELES_GRAVEDAD } from '../utils/formato'

export function DashboardEmergenciasPage() {
  const [tablero, setTablero] = useState<Tablero | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [nivelGravedad, setNivelGravedad] = useState<FiltrosReportes['nivel_gravedad']>()
  const [formatoExportar, setFormatoExportar] = useState<FormatoReporte>('csv')
  const [exportando, setExportando] = useState(false)
  const [errorExportar, setErrorExportar] = useState<string | null>(null)

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
      try {
        const datos = await obtenerTablero(filtros)
        if (vigente) setTablero(datos)
      } catch (fallo) {
        if (vigente) {
          setTablero(null)
          setError(describirError(fallo))
        }
      } finally {
        if (vigente) setCargando(false)
      }
    }

    void cargar()
    return () => { vigente = false }
  }, [filtros])

  async function descargarReporte() {
    setExportando(true)
    setErrorExportar(null)
    try {
      const archivo = await exportarReporteCompleto(filtros, formatoExportar)
      const url = URL.createObjectURL(archivo)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `reporte-completo.${formatoExportar}`
      enlace.click()
      URL.revokeObjectURL(url)
    } catch (fallo) {
      setErrorExportar(describirError(fallo))
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
          <label className="flex flex-col gap-1 text-sm text-slate-300">Nivel de gravedad<select value={nivelGravedad ?? ''} onChange={(evento) => setNivelGravedad(evento.target.value ? evento.target.value as FiltrosReportes['nivel_gravedad'] : undefined)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white"><option value="">Todas</option>{NIVELES_GRAVEDAD.map((nivel) => <option key={nivel.valor} value={nivel.valor}>{nivel.etiqueta}</option>)}</select></label>
        </div>
        <div className="mt-4 border-t border-slate-700 pt-4">
          <p className="mb-2 text-sm font-semibold text-slate-300">Exportar reporte filtrado</p>
          <p className="mb-3 text-xs text-slate-400">Descargá todas las métricas del dashboard usando los filtros seleccionados.</p>
          <div className="flex flex-col gap-2 sm:flex-row"><select value={formatoExportar} onChange={(evento) => setFormatoExportar(evento.target.value as FormatoReporte)} className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white"><option value="csv">CSV</option><option value="json">JSON</option></select><button type="button" onClick={() => void descargarReporte()} disabled={exportando} className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50">{exportando ? 'Exportando...' : 'Descargar reporte completo'}</button></div>
          {errorExportar !== null && <p role="alert" className="mt-2 rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">No se pudo exportar el reporte. {errorExportar}</p>}
        </div>
      </div>
      {cargando && <p className="rounded-xl border border-slate-700 bg-slate-800 p-6 text-sm text-slate-400">Cargando dashboard...</p>}
      {!cargando && error !== null && <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">No se pudo cargar el dashboard. {error}</p>}
      {!cargando && error === null && tablero !== null && (
        <>
          <DashboardEmergencias resumen={tablero.resumen} />
          <ReportesDashboard tablero={tablero} />
        </>
      )}
    </section>
  )
}
