import type { EstadoEmergencia, Indicador, ResumenTablero } from '../types'
import { etiquetaDeEstado, etiquetaDeGravedad, formatearDuracion, NIVELES_GRAVEDAD } from '../utils/formato'
import { MetaIndicador } from './MetaIndicador'

interface DashboardEmergenciasProps {
  resumen: ResumenTablero
}

const ORDEN_ESTADOS = [
  'esperando_lotes',
  'esperando_ofertas',
  'esperando_adjudicacion',
  'en_proceso',
  'resuelta',
]

const claseTarjeta = 'rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl'

function Kpi({ titulo, valor, detalle, nota, indicador }: {
  titulo: string
  valor: string
  detalle?: string
  nota?: string
  indicador: Indicador
}) {
  return (
    <div className={claseTarjeta}>
      <p className="text-sm text-slate-400">{titulo}</p>
      <p className="mt-1 text-3xl font-bold text-cyan-400">
        {valor}
        {detalle && <span className="ml-2 text-sm font-normal text-slate-400">{detalle}</span>}
      </p>
      {nota && <p className="mt-1 text-xs text-amber-300">{nota}</p>}
      <MetaIndicador indicador={indicador} />
    </div>
  )
}

const casos = (n: number) => `(${n} ${n === 1 ? 'caso' : 'casos'})`

function EvolucionAperturasCierres({ indicador }: { indicador: ResumenTablero['evolucion'] }) {
  const puntos = indicador.filas
  const ancho = 640
  const alto = 280
  const margen = { superior: 24, derecho: 20, inferior: 44, izquierdo: 42 }
  const anchoGrafico = ancho - margen.izquierdo - margen.derecho
  const altoGrafico = alto - margen.superior - margen.inferior
  const maximo = Math.max(...puntos.flatMap((punto) => [punto.aperturas, punto.cierres]), 1)
  const posicionX = (indice: number) =>
    margen.izquierdo + (puntos.length > 1 ? indice / (puntos.length - 1) : 0.5) * anchoGrafico
  const posicionY = (valor: number) => margen.superior + altoGrafico - (valor / maximo) * altoGrafico
  const puntosAperturas = puntos.map((punto, indice) => `${posicionX(indice)},${posicionY(punto.aperturas)}`).join(' ')
  const puntosCierres = puntos.map((punto, indice) => `${posicionX(indice)},${posicionY(punto.cierres)}`).join(' ')

  return (
    <section className={claseTarjeta} aria-labelledby="titulo-evolucion">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="titulo-evolucion" className="text-lg font-bold text-cyan-400">Evolución de aperturas y cierres</h2>
        <div className="flex gap-4 text-xs" aria-label="Referencias del gráfico">
          <span className="text-amber-300">● Aperturas</span>
          <span className="text-emerald-300">● Cierres</span>
        </div>
      </div>
      <MetaIndicador indicador={indicador} />
      {puntos.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No hay datos de evolución para mostrar.</p>
      ) : (
        <>
          <div className="mt-4 overflow-x-auto">
            <svg
              className="min-w-[560px]"
              viewBox={`0 0 ${ancho} ${alto}`}
              role="img"
              aria-labelledby="titulo-evolucion descripcion-evolucion"
            >
              <desc id="descripcion-evolucion">Líneas superpuestas con la cantidad de emergencias abiertas y cerradas por día.</desc>
              <line x1={margen.izquierdo} y1={margen.superior} x2={margen.izquierdo} y2={alto - margen.inferior} className="stroke-slate-500" />
              <line x1={margen.izquierdo} y1={alto - margen.inferior} x2={ancho - margen.derecho} y2={alto - margen.inferior} className="stroke-slate-500" />
              <text x={margen.izquierdo - 8} y={margen.superior + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{maximo}</text>
              <text x={margen.izquierdo - 8} y={alto - margen.inferior + 4} textAnchor="end" className="fill-slate-400 text-[11px]">0</text>
              <polyline points={puntosAperturas} fill="none" className="stroke-amber-300" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points={puntosCierres} fill="none" className="stroke-emerald-300" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              {puntos.map((punto, indice) => (
                <g key={punto.fecha}>
                  <circle cx={posicionX(indice)} cy={posicionY(punto.aperturas)} r="4" className="fill-amber-300" />
                  <circle cx={posicionX(indice)} cy={posicionY(punto.cierres)} r="4" className="fill-emerald-300" />
                  <text x={posicionX(indice)} y={alto - margen.inferior + 24} textAnchor="middle" className="fill-slate-400 text-[10px]">{punto.fecha}</text>
                </g>
              ))}
            </svg>
          </div>
          <table className="sr-only">
            <caption>Aperturas y cierres de emergencias por día</caption>
            <thead><tr><th scope="col">Fecha</th><th scope="col">Aperturas</th><th scope="col">Cierres</th></tr></thead>
            <tbody>
              {puntos.map((punto) => (
                <tr key={punto.fecha}><td>{punto.fecha}</td><td>{punto.aperturas}</td><td>{punto.cierres}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function EmergenciasPorEstadoYGravedad({ indicador }: { indicador: ResumenTablero['por_estado_y_gravedad'] }) {
  const filas = indicador.filas
  const posicion = (estado: string) => {
    const indice = ORDEN_ESTADOS.indexOf(estado)
    return indice === -1 ? ORDEN_ESTADOS.length : indice
  }
  const estados = Array.from(new Set(filas.map((fila) => fila.estado))).sort((a, b) => posicion(a) - posicion(b))
  const cantidad = (estado: string, gravedad: string) =>
    filas.filter((fila) => fila.estado === estado && fila.nivel_gravedad === gravedad)
      .reduce((total, fila) => total + fila.cantidad, 0)

  return (
    <section className={claseTarjeta} aria-labelledby="titulo-estado-gravedad">
      <h2 id="titulo-estado-gravedad" className="text-lg font-bold text-cyan-400">Emergencias por estado y gravedad</h2>
      <MetaIndicador indicador={indicador} />
      {filas.length === 0 ? <p className="mt-4 text-sm text-slate-400">No hay datos de estado y gravedad para mostrar.</p> : (
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><caption className="sr-only">Cantidad de emergencias por estado y nivel de gravedad</caption><thead><tr className="border-b border-slate-700 text-slate-400"><th className="px-3 py-2">Estado</th>{NIVELES_GRAVEDAD.map(({ valor }) => <th key={valor} className="px-3 py-2 text-right">{etiquetaDeGravedad(valor)}</th>)}</tr></thead><tbody>
          {estados.map((estado) => <tr key={estado} className="border-b border-slate-800"><th scope="row" className="px-3 py-3 font-medium text-slate-200">{etiquetaDeEstado(estado as EstadoEmergencia)}</th>{NIVELES_GRAVEDAD.map(({ valor }) => <td key={valor} className="px-3 py-3 text-right font-mono text-cyan-300">{cantidad(estado, valor)}</td>)}</tr>)}
        </tbody></table></div>
      )}
    </section>
  )
}

/** Resumen del tablero del Auditor: indicadores principales, matriz estado/gravedad y evolución. */
export function DashboardEmergencias({ resumen }: DashboardEmergenciasProps) {
  const { prioridad_promedio_abiertas: prioridad, antiguedad_abiertas_horas: antiguedad, resolucion_horas: resolucion } = resumen
  const sinFecha = resolucion.sin_fecha_cierre

  return (
    <section className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Kpi titulo="Emergencias totales" valor={String(resumen.total.valor)} indicador={resumen.total} />
        <Kpi titulo="Abiertas" valor={String(resumen.abiertas.valor)} indicador={resumen.abiertas} />
        <Kpi titulo="Resueltas" valor={String(resumen.resueltas.valor)} indicador={resumen.resueltas} />
        <Kpi
          titulo="Prioridad promedio de abiertas"
          valor={prioridad.valor === null ? '—' : prioridad.valor.toFixed(2)}
          detalle={casos(prioridad.n)}
          indicador={prioridad}
        />
        <Kpi
          titulo="Antigüedad promedio de abiertas"
          valor={antiguedad.promedio === null ? '—' : formatearDuracion(antiguedad.promedio)}
          detalle={casos(antiguedad.n)}
          indicador={antiguedad}
        />
        <Kpi
          titulo="Tiempo de resolución de finalizadas"
          valor={resolucion.promedio === null ? '—' : formatearDuracion(resolucion.promedio)}
          detalle={casos(resolucion.n)}
          nota={sinFecha.length > 0
            ? `${sinFecha.length} ${sinFecha.length === 1 ? 'resuelta' : 'resueltas'} sin fecha de cierre (${sinFecha.map((id) => `#${id}`).join(', ')})`
            : undefined}
          indicador={resolucion}
        />
      </div>

      <EmergenciasPorEstadoYGravedad indicador={resumen.por_estado_y_gravedad} />
      <EvolucionAperturasCierres indicador={resumen.evolucion} />
    </section>
  )
}
