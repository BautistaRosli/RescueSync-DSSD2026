import type {
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

export interface DatosReportesDashboard {
  emergencias?: ReporteEmergenciaGravedad[]
  suministros?: ReporteSuministroMovilizado[]
  consorcios?: ReporteConsorcios
  proyectos?: ReporteProyecto[]
  cobertura?: ReporteCoberturaLotes
  tiempoPublicacion?: ReporteTiempoPublicacion
  tiempoAdjudicacion?: ReporteTiempoAdjudicacion
  rankingOngs?: ReporteRankingOng[]
  demandaOferta?: ReporteDemandaOferta[]
  errores: string[]
}

const panel = 'rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl'

function Titulo({ children }: { children: string }) {
  return <h2 className="text-lg font-bold text-cyan-400">{children}</h2>
}

function AvisoVacio() {
  return <p className="mt-4 text-sm text-slate-400">No hay datos para mostrar.</p>
}

function Barra({ etiqueta, valor, maximo, color = 'bg-cyan-400' }: { etiqueta: string; valor: number; maximo: number; color?: string }) {
  const porcentaje = maximo > 0 ? Math.min(100, (valor / maximo) * 100) : 0
  return (
    <li className="flex flex-col gap-2">
      <div className="flex justify-between gap-3 text-sm"><span className="text-slate-200">{etiqueta}</span><span className="font-mono text-cyan-300">{valor}</span></div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-700"><div className={`h-full rounded-full ${color}`} style={{ width: `${porcentaje}%` }} aria-hidden="true" /></div>
    </li>
  )
}

function GraficoEmergencias({ datos }: { datos: ReporteEmergenciaGravedad[] }) {
  const agrupados = new Map<string, number>()
  datos.forEach((item) => agrupados.set(`${item.estado} · ${item.nivel_gravedad}`, (agrupados.get(`${item.estado} · ${item.nivel_gravedad}`) ?? 0) + item.cantidad))
  const filas = Array.from(agrupados.entries())
  const maximo = Math.max(...filas.map(([, valor]) => valor), 1)
  return <section className={panel}><Titulo>Emergencias por estado y gravedad</Titulo>{filas.length === 0 ? <AvisoVacio /> : <><ul className="mt-5 flex flex-col gap-4">{filas.map(([etiqueta, valor]) => <Barra key={etiqueta} etiqueta={etiqueta} valor={valor} maximo={maximo} color="bg-amber-400" />)}</ul><table className="sr-only"><caption>Emergencias agrupadas por estado y gravedad</caption><tbody>{filas.map(([etiqueta, valor]) => <tr key={etiqueta}><th>{etiqueta}</th><td>{valor}</td></tr>)}</tbody></table></>}</section>
}

function GraficoSuministros({ datos }: { datos: ReporteSuministroMovilizado[] }) {
  const filas = datos.map((item) => ({ ...item, etiqueta: `${item.mes} · ${item.tipo_recurso}` }))
  const maximo = Math.max(...filas.map((item) => item.cantidad_adjudicada), 1)
  return <section className={panel}><Titulo>Suministros movilizados</Titulo>{filas.length === 0 ? <AvisoVacio /> : <><ul className="mt-5 flex max-h-80 flex-col gap-4 overflow-y-auto">{filas.map((item) => <Barra key={item.etiqueta} etiqueta={item.etiqueta} valor={item.cantidad_adjudicada} maximo={maximo} color="bg-blue-400" />)}</ul><table className="sr-only"><caption>Suministros movilizados por mes y recurso</caption><thead><tr><th>Mes</th><th>Recurso</th><th>Cantidad</th></tr></thead><tbody>{filas.map((item) => <tr key={item.etiqueta}><td>{item.mes}</td><td>{item.tipo_recurso}</td><td>{item.cantidad_adjudicada}</td></tr>)}</tbody></table></>}</section>
}

function GraficoDemandaOferta({ datos }: { datos: ReporteDemandaOferta[] }) {
  const maximo = Math.max(...datos.flatMap((item) => [item.cantidad_pedida, item.cantidad_ofrecida]), 1)
  return <section className={panel}><div className="flex flex-wrap justify-between gap-2"><Titulo>Demanda vs. oferta</Titulo><span className="text-xs text-slate-400">Pedido / ofrecido</span></div>{datos.length === 0 ? <AvisoVacio /> : <div className="mt-5 flex flex-col gap-4">{datos.map((item) => <div key={item.tipo_recurso}><div className="mb-1 flex justify-between text-sm"><span>{item.tipo_recurso}</span><span className="text-slate-400">{item.cantidad_pedida} / {item.cantidad_ofrecida}</span></div><div className="flex h-3 gap-1"><div className="rounded-full bg-fuchsia-400" style={{ width: `${(item.cantidad_pedida / maximo) * 100}%` }} title={`Pedido: ${item.cantidad_pedida}`} /><div className="rounded-full bg-emerald-400" style={{ width: `${(item.cantidad_ofrecida / maximo) * 100}%` }} title={`Ofrecido: ${item.cantidad_ofrecida}`} /></div></div>)}</div>}<table className="sr-only"><caption>Demanda y oferta por recurso</caption><thead><tr><th>Recurso</th><th>Pedido</th><th>Ofrecido</th></tr></thead><tbody>{datos.map((item) => <tr key={item.tipo_recurso}><td>{item.tipo_recurso}</td><td>{item.cantidad_pedida}</td><td>{item.cantidad_ofrecida}</td></tr>)}</tbody></table></section>
}

function TarjetasTiempos({ publicacion, adjudicacion }: { publicacion?: ReporteTiempoPublicacion; adjudicacion?: ReporteTiempoAdjudicacion }) {
  return <div className="grid gap-4 sm:grid-cols-2"><section className={panel}><Titulo>Tiempo de publicación</Titulo>{publicacion ? <div className="mt-4 grid grid-cols-3 gap-2 text-center"><div><strong className="block text-2xl text-cyan-300">{publicacion.promedio_horas.toFixed(1)}</strong><span className="text-xs text-slate-400">Promedio h</span></div><div><strong className="block text-2xl text-cyan-300">{publicacion.minimo_horas.toFixed(1)}</strong><span className="text-xs text-slate-400">Mínimo h</span></div><div><strong className="block text-2xl text-cyan-300">{publicacion.maximo_horas.toFixed(1)}</strong><span className="text-xs text-slate-400">Máximo h</span></div></div> : <AvisoVacio />}</section><section className={panel}><Titulo>Tiempo de adjudicación</Titulo>{adjudicacion ? <p className="mt-4 text-4xl font-bold text-cyan-300">{adjudicacion.promedio_horas.toFixed(1)} <span className="text-base font-normal text-slate-400">horas promedio</span></p> : <AvisoVacio />}</section></div>
}

function TablaProyectos({ datos }: { datos: ReporteProyecto[] }) {
  return <section className={panel}><Titulo>Proyectos y avance</Titulo>{datos.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Avance de proyectos por emergencia</caption><thead className="text-xs uppercase text-slate-400"><tr><th className="px-2 py-2">Emergencia / zona</th><th className="px-2 py-2">Total</th><th className="px-2 py-2">Finalizados</th><th className="px-2 py-2">Pendientes</th><th className="px-2 py-2">Estado</th></tr></thead><tbody>{datos.map((item) => <tr key={item.emergencia_id} className="border-t border-slate-700"><th className="px-2 py-3 font-medium">#{item.emergencia_id} · {item.zona_afectada}</th><td className="px-2 py-3">{item.items_totales}</td><td className="px-2 py-3 text-emerald-300">{item.items_finalizados}</td><td className="px-2 py-3 text-amber-300">{item.items_pendientes}</td><td className="px-2 py-3">{item.resuelta ? 'Resuelta' : 'En curso'}</td></tr>)}</tbody></table></div>}</section>
}

function TablaCobertura({ datos }: { datos: ReporteCoberturaLotes }) {
  const filas = datos.lotes
  return <section className={panel}><div className="flex flex-wrap items-center justify-between gap-2"><Titulo>Cobertura de lotes</Titulo><span className="rounded-full border border-red-400/40 px-2 py-1 text-xs text-red-300">Sin cubrir: {datos.lotes_sin_cubrir.length}</span></div>{filas.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Cobertura de cada lote, incluidos los lotes sin cubrir</caption><thead className="text-xs uppercase text-slate-400"><tr><th className="px-2 py-2">Lote</th><th className="px-2 py-2">Recurso</th><th className="px-2 py-2">Requerida</th><th className="px-2 py-2">Ofrecida</th><th className="px-2 py-2">Cobertura</th></tr></thead><tbody>{filas.map((item) => <tr key={item.lote_id} className={`border-t border-slate-700 ${datos.lotes_sin_cubrir.some((sinCubrir) => sinCubrir.lote_id === item.lote_id) ? 'bg-red-500/10' : ''}`}><th className="px-2 py-3">#{item.lote_id} / E{item.emergencia_id}</th><td className="px-2 py-3">{item.tipo_recurso}</td><td className="px-2 py-3">{item.cantidad_requerida}</td><td className="px-2 py-3">{item.cantidad_ofrecida}</td><td className="px-2 py-3">{item.porcentaje_cobertura.toFixed(1)}%</td></tr>)}</tbody></table></div>}</section>
}

function RankingOngs({ datos }: { datos: ReporteRankingOng[] }) {
  return <section className={panel}><Titulo>Ranking de ONG</Titulo>{datos.length === 0 ? <AvisoVacio /> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Ranking de ONG por actividad</caption><thead className="text-xs uppercase text-slate-400"><tr><th className="px-2 py-2">Organización</th><th className="px-2 py-2">Presentadas</th><th className="px-2 py-2">Adjudicadas</th><th className="px-2 py-2">Consorcios</th><th className="px-2 py-2">Finalizadas</th></tr></thead><tbody>{datos.map((item) => <tr key={item.organizacion_id} className="border-t border-slate-700"><th className="px-2 py-3">{item.organizacion_nombre}</th><td className="px-2 py-3">{item.ofertas_presentadas}</td><td className="px-2 py-3">{item.ofertas_adjudicadas}</td><td className="px-2 py-3">{item.participaciones_consorcios}</td><td className="px-2 py-3">{item.actividades_finalizadas}</td></tr>)}</tbody></table></div>}</section>
}

export function ReportesDashboard({ datos }: { datos: DatosReportesDashboard }) {
  return <section className="flex flex-col gap-4" aria-label="Reportes del director auditor"><div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-4"><h2 className="font-bold text-cyan-300">Reportes operativos</h2><p className="mt-1 text-sm text-slate-300">Indicadores de emergencias, recursos, ofertas y proyectos.</p>{datos.errores.length > 0 && <p role="alert" className="mt-2 text-sm text-amber-300">Algunos reportes no pudieron cargarse: {datos.errores.join(' · ')}</p>}</div><div className="grid gap-4 lg:grid-cols-2"><GraficoEmergencias datos={datos.emergencias ?? []} /><GraficoSuministros datos={datos.suministros ?? []} /></div><div className="grid gap-4 lg:grid-cols-2"><GraficoDemandaOferta datos={datos.demandaOferta ?? []} /><RankingOngs datos={datos.rankingOngs ?? []} /></div>{datos.consorcios && <section className={panel}><Titulo>Consorcios</Titulo><div className="mt-4 grid gap-3 sm:grid-cols-3"><div><span className="text-sm text-slate-400">Ofertas adjudicadas</span><strong className="mt-1 block text-3xl text-cyan-300">{datos.consorcios.total_ofertas_adjudicadas}</strong></div><div><span className="text-sm text-slate-400">Ofertas conjuntas</span><strong className="mt-1 block text-3xl text-cyan-300">{datos.consorcios.ofertas_conjuntas}</strong></div><div><span className="text-sm text-slate-400">Porcentaje consorcios</span><strong className="mt-1 block text-3xl text-cyan-300">{datos.consorcios.porcentaje_consorcios.toFixed(1)}%</strong></div></div></section>}<TarjetasTiempos publicacion={datos.tiempoPublicacion} adjudicacion={datos.tiempoAdjudicacion} /><TablaProyectos datos={datos.proyectos ?? []} />{datos.cobertura && <TablaCobertura datos={datos.cobertura} />}</section>
}
