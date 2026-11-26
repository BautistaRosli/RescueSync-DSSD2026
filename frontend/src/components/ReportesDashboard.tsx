import type {
  BonitaTablero,
  EstadoCasoBonita,
  EstadoEmergencia,
  ProyectosTablero,
  RecursosTablero,
  Tablero,
} from '../types'
import { etiquetaDeEstado, formatearDuracion, formatearNumero } from '../utils/formato'
import { MetaIndicador } from './MetaIndicador'

const panel = 'rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl'
const celda = 'px-2 py-3'
const encabezado = 'px-2 py-2'

function Titulo({ children }: { children: string }) {
  return <h2 className="text-lg font-bold text-cyan-400">{children}</h2>
}

function AvisoVacio() {
  return <p className="mt-4 text-sm text-slate-400">No hay datos para mostrar.</p>
}

const textoUnidad = (unidad: string | null) => unidad ?? 'sin unidad'
const textoOpcional = (valor: number | null, formatear: (valor: number) => string = formatearNumero) =>
  valor === null ? '—' : formatear(valor)
const textoEstado = (estado: string | null) => etiquetaDeEstado(estado as EstadoEmergencia | null)

function Barra({ etiqueta, valor, porcentaje, color = 'bg-cyan-400' }: { etiqueta: string; valor: string; porcentaje: number; color?: string }) {
  return <li className="flex flex-col gap-2"><div className="flex justify-between gap-3 text-sm"><span className="text-slate-200">{etiqueta}</span><span className="font-mono text-cyan-300">{valor}</span></div><div className="h-3 overflow-hidden rounded-full bg-slate-700"><div className={`h-full rounded-full ${color}`} style={{ width: `${porcentaje}%` }} aria-hidden="true" /></div></li>
}

function CoberturaPorLote({ indicador }: { indicador: RecursosTablero['por_lote'] }) {
  const filas = indicador.filas
  const incompleto = (porcentaje: number | null) => porcentaje !== null && porcentaje < 100
  return <section className={panel}><Titulo>Cobertura por lote</Titulo><MetaIndicador indicador={indicador} />{filas.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Cobertura confirmada de cada lote</caption><thead className="text-xs uppercase text-slate-400"><tr><th className={encabezado}>Lote</th><th className={encabezado}>Recurso</th><th className={encabezado}>Unidad</th><th className={encabezado}>Pedido</th><th className={encabezado}>Ofertado</th><th className={encabezado}>Verificado</th><th className={encabezado}>Cubierto confirmado</th><th className={encabezado}>Cobertura</th></tr></thead><tbody>{filas.map((item) => <tr key={item.lote_id} className={`border-t border-slate-700 ${incompleto(item.porcentaje_cobertura) ? 'bg-red-500/10' : ''}`}><th className={celda}>#{item.lote_id} / E{item.emergencia_id}</th><td className={celda}>{item.tipo_recurso}</td><td className={celda}>{textoUnidad(item.unidad)}</td><td className={celda}>{formatearNumero(item.pedido)}</td><td className={celda}>{formatearNumero(item.ofertado)}</td><td className={celda}>{textoOpcional(item.verificado)}</td><td className={celda}>{formatearNumero(item.cubierto_confirmado)}</td><td className={`${celda} ${incompleto(item.porcentaje_cobertura) ? 'text-red-300' : ''}`}>{textoOpcional(item.porcentaje_cobertura, (valor) => `${valor.toFixed(1)}%`)}</td></tr>)}</tbody></table></div>}</section>
}

function RecursosPorMes({ recursos }: { recursos: RecursosTablero }) {
  const { filas } = recursos.totales
  const campo = recursos.etiqueta_recursos === 'Recursos entregados' ? 'entregado' : 'reservado'
  // El máximo de cada barra se calcula por unidad: nunca se comparan cantidades de unidades distintas.
  const maximoPorUnidad = new Map<string, number>()
  filas.forEach((fila) => maximoPorUnidad.set(textoUnidad(fila.unidad), Math.max(maximoPorUnidad.get(textoUnidad(fila.unidad)) ?? 0, fila[campo])))
  const clave = (fila: (typeof filas)[number]) => `${fila.mes ?? 'sin-mes'}-${fila.tipo_recurso}-${fila.tipo_recurso_id ?? 'sin-id'}-${fila.unidad ?? 'sin-unidad'}`
  const etiqueta = (fila: (typeof filas)[number]) => `${fila.mes ?? 'Sin fecha'} · ${fila.tipo_recurso} (${textoUnidad(fila.unidad)})`
  return <section className={panel}><Titulo>{recursos.etiqueta_recursos}</Titulo><MetaIndicador indicador={recursos.totales} />{filas.length === 0 ? <AvisoVacio /> : <><ul className="mt-5 flex max-h-80 flex-col gap-4 overflow-y-auto">{filas.map((fila) => { const maximo = maximoPorUnidad.get(textoUnidad(fila.unidad)) ?? 0; return <Barra key={clave(fila)} etiqueta={etiqueta(fila)} valor={`${formatearNumero(fila[campo])} ${textoUnidad(fila.unidad)}`} porcentaje={maximo > 0 ? (fila[campo] / maximo) * 100 : 0} color="bg-blue-400" /> })}</ul><div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Recursos por mes, tipo y unidad</caption><thead className="text-xs uppercase text-slate-400"><tr><th className={encabezado}>Mes</th><th className={encabezado}>Recurso</th><th className={encabezado}>Unidad</th><th className={encabezado}>Ofertado</th><th className={encabezado}>Verificado</th><th className={encabezado}>Reservado</th><th className={encabezado}>Entregado</th></tr></thead><tbody>{filas.map((fila) => <tr key={clave(fila)} className="border-t border-slate-700"><th className={celda}>{fila.mes ?? 'Sin fecha'}</th><td className={celda}>{fila.tipo_recurso}</td><td className={celda}>{textoUnidad(fila.unidad)}</td><td className={celda}>{formatearNumero(fila.ofertado)}</td><td className={celda}>{formatearNumero(fila.verificado)}</td><td className={celda}>{formatearNumero(fila.reservado)}</td><td className={celda}>{formatearNumero(fila.entregado)}</td></tr>)}</tbody></table></div></>}</section>
}

function TablaProyectos({ indicador }: { indicador: ProyectosTablero['proyectos'] }) {
  const filas = indicador.filas
  return <section className={panel}><Titulo>Proyectos y avance</Titulo><MetaIndicador indicador={indicador} />{filas.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Avance de proyectos por emergencia</caption><thead className="text-xs uppercase text-slate-400"><tr><th className={encabezado}>Emergencia / zona</th><th className={encabezado}>Estado</th><th className={encabezado}>Ítems finalizados</th><th className={encabezado}>Confirmado / entregado</th><th className={encabezado}>Tiempo de resolución</th></tr></thead><tbody>{filas.map((item) => <tr key={item.emergencia_id} className="border-t border-slate-700"><th className={`${celda} font-medium`}>#{item.emergencia_id} · {item.zona_afectada}</th><td className={celda}>{textoEstado(item.estado)}</td><td className={celda}><span className="text-emerald-300">{item.items_finalizados}</span> / {item.items_totales}</td><td className={celda}>{item.cantidades.length === 0 ? '—' : <ul className="flex flex-col gap-1">{item.cantidades.map((cantidad) => <li key={`${cantidad.tipo_recurso}-${cantidad.unidad ?? 'sin-unidad'}`}>{cantidad.tipo_recurso}: {formatearNumero(cantidad.confirmado)} / {formatearNumero(cantidad.entregado)} {textoUnidad(cantidad.unidad)}</li>)}</ul>}</td><td className={celda}>{textoOpcional(item.resolucion_horas, formatearDuracion)}</td></tr>)}</tbody></table></div>}</section>
}

function Consorcios({ indicador }: { indicador: ProyectosTablero['consorcios'] }) {
  const porcentaje = indicador.porcentaje === null ? 0 : Math.min(Math.max(indicador.porcentaje, 0), 100)
  return <section className={panel}><Titulo>Consorcios</Titulo><MetaIndicador indicador={indicador} /><p className="mt-4 text-sm text-slate-200"><strong className="text-2xl text-fuchsia-300">{indicador.resueltas_con_consorcio}</strong> de <strong className="text-2xl text-cyan-300">{indicador.emergencias_resueltas}</strong> emergencias resueltas se atendieron con al menos un consorcio ({indicador.porcentaje === null ? '—' : `${indicador.porcentaje.toFixed(1)}%`})</p><div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-700" aria-hidden="true"><div className="h-full rounded-full bg-fuchsia-400" style={{ width: `${porcentaje}%` }} /></div></section>
}

function RankingOngs({ indicador }: { indicador: ProyectosTablero['ranking_ongs'] }) {
  const filas = indicador.filas
  return <section className={panel}><Titulo>Ranking de ONG</Titulo><MetaIndicador indicador={indicador} />{filas.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Cantidad confirmada por ONG, recurso y unidad</caption><thead className="text-xs uppercase text-slate-400"><tr><th className={encabezado}>Organización</th><th className={encabezado}>Recurso</th><th className={encabezado}>Unidad</th><th className={encabezado}>Cantidad confirmada</th></tr></thead><tbody>{filas.map((item) => <tr key={`${item.organizacion_id}-${item.tipo_recurso}-${item.unidad ?? 'sin-unidad'}`} className="border-t border-slate-700"><th className={celda}>{item.organizacion_nombre}</th><td className={celda}>{item.tipo_recurso}</td><td className={celda}>{textoUnidad(item.unidad)}</td><td className={celda}>{formatearNumero(item.cantidad_confirmada)}</td></tr>)}</tbody></table></div>}</section>
}

const ESTADOS_BONITA: Record<EstadoCasoBonita, string> = {
  activo: 'Activo', completed: 'Finalizado', cancelado: 'Cancelado', no_encontrado: 'No encontrado',
}

function EjecucionBonita({ datos }: { datos: BonitaTablero }) {
  if (!datos.disponible) {
    return <section className={panel}><Titulo>Ejecución en Bonita</Titulo><MetaIndicador indicador={datos} /><p role="alert" className="mt-4 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">Bonita no disponible: {datos.error ?? 'sin detalle'}</p></section>
  }
  const conDatos = datos.tiempos_por_etapa.filter((item) => item.n > 0 && item.promedio_horas !== null)
  const maximo = Math.max(0, ...conDatos.map((item) => item.promedio_horas ?? 0))
  return <section className={panel}><Titulo>Ejecución en Bonita</Titulo><MetaIndicador indicador={datos} /><div className="mt-4 grid gap-3 sm:grid-cols-4"><div><span className="text-sm text-slate-400">Casos activos</span><strong className="mt-1 block text-3xl text-amber-300">{datos.casos_activos}</strong></div><div><span className="text-sm text-slate-400">Casos finalizados</span><strong className="mt-1 block text-3xl text-emerald-300">{datos.casos_finalizados}</strong></div><div><span className="text-sm text-slate-400">Casos cancelados</span><strong className="mt-1 block text-3xl text-red-300">{datos.casos_cancelados}</strong></div><div><span className="text-sm text-slate-400">Casos por camino alternativo</span><strong className="mt-1 block text-3xl text-fuchsia-300">{datos.casos_camino_alternativo}</strong></div></div><div className="mt-5"><h3 className="text-sm font-semibold text-slate-300">Tiempo promedio por etapa</h3>{datos.tiempos_por_etapa.length === 0 ? <AvisoVacio /> : <ul className="mt-4 flex flex-col gap-4">{datos.tiempos_por_etapa.map((item) => <li key={item.etapa}><div className="flex justify-between gap-3 text-sm"><span className="text-slate-200">{item.etapa} <span className="text-slate-500">({item.n})</span></span><span className="font-mono text-cyan-300">{item.n === 0 || item.promedio_horas === null ? '—' : formatearDuracion(item.promedio_horas)}</span></div><div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-cyan-400" style={{ width: `${maximo > 0 && item.promedio_horas !== null ? (item.promedio_horas / maximo) * 100 : 0}%` }} aria-hidden="true" /></div></li>)}</ul>}</div><div className="mt-5"><h3 className="text-sm font-semibold text-slate-300">Verificación caso por caso</h3>{datos.verificacion.length === 0 ? <AvisoVacio /> : <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Estado local y estado en Bonita de cada caso</caption><thead className="text-xs uppercase text-slate-400"><tr><th className={encabezado}>Emergencia</th><th className={encabezado}>Caso</th><th className={encabezado}>Estado local</th><th className={encabezado}>Estado Bonita</th><th className={encabezado}>Tiempo</th></tr></thead><tbody>{datos.verificacion.map((item) => <tr key={`${item.emergencia_id}-${item.bonita_case_id}`} className="border-t border-slate-700"><th className={celda}>#{item.emergencia_id}</th><td className={`${celda} font-mono`}>{item.bonita_case_id}</td><td className={celda}>{textoEstado(item.estado_local)}</td><td className={celda}>{ESTADOS_BONITA[item.estado_bonita] ?? item.estado_bonita}</td><td className={celda}>{textoOpcional(item.resolucion_horas, formatearDuracion)}</td></tr>)}</tbody></table></div>}</div></section>
}

/** Paneles de recursos, proyectos, ONG y Bonita del tablero del Auditor. */
export function ReportesDashboard({ tablero }: { tablero: Tablero }) {
  const { recursos, proyectos, bonita } = tablero
  return <section className="flex flex-col gap-4" aria-label="Reportes del director auditor"><div className="grid gap-4 lg:grid-cols-2"><CoberturaPorLote indicador={recursos.por_lote} /><RecursosPorMes recursos={recursos} /></div><TablaProyectos indicador={proyectos.proyectos} /><div className="grid gap-4 lg:grid-cols-2"><Consorcios indicador={proyectos.consorcios} /><RankingOngs indicador={proyectos.ranking_ongs} /></div><EjecucionBonita datos={bonita} /></section>
}
