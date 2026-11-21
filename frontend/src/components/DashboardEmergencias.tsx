import type {
  DashboardEmergencias,
  EmergenciaRespuesta,
  DemandaVsOfertaPorRecurso,
  RecursoAdjudicadoPorMes,
} from '../types'

interface DashboardEmergenciasProps {
  datos: DashboardEmergencias
}

function EmergenciaResumen({ emergencia }: { emergencia: EmergenciaRespuesta }) {
  return (
    <li className="rounded-lg border border-slate-700 bg-slate-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-white">{emergencia.zona_afectada}</h3>
        <span className="font-mono text-xs text-slate-500">#{emergencia.id}</span>
      </div>
      <p className="mt-2 text-sm text-slate-400">{emergencia.descripcion_inicial}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-cyan-300">
        <span className="rounded-full border border-cyan-500/40 px-2 py-1">
          Gravedad: {emergencia.nivel_gravedad}
        </span>
        <span className="rounded-full border border-slate-700 px-2 py-1">
          Estado: {emergencia.estado ?? 'Sin estado'}
        </span>
      </div>
    </li>
  )
}

function etiquetaDeEstado(estado: string): string {
  const etiquetas: Record<string, string> = {
    esperando_lotes: 'Esperando lotes',
    esperando_ofertas: 'Esperando ofertas',
    esperando_adjudicacion: 'Esperando adjudicación',
    en_proceso: 'En proceso',
    resuelta: 'Resuelta',
  }
  return etiquetas[estado] ?? estado
}

function etiquetaDeGravedad(gravedad: string): string {
  const etiquetas: Record<string, string> = {
    baja: 'Baja',
    media: 'Media',
    alta: 'Alta',
    critica: 'Crítica',
  }
  return etiquetas[gravedad] ?? gravedad
}

function numero(valor: number): string {
  return valor.toLocaleString('es-AR', { maximumFractionDigits: 2 })
}

function decimal(valor: number | string): string {
  return Number(valor).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const ORDEN_ESTADOS = [
  'esperando_lotes',
  'esperando_ofertas',
  'esperando_adjudicacion',
  'en_proceso',
  'resuelta',
]

function BarraHorizontal({
  etiqueta,
  valor,
  maximo,
  color = 'bg-cyan-400',
}: {
  etiqueta: string
  valor: number
  maximo: number
  color?: string
}) {
  const porcentaje = maximo > 0 ? (valor / maximo) * 100 : 0

  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-slate-200">{etiqueta}</span>
        <span className="font-mono text-cyan-300">{valor}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-700">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${porcentaje}%` }}
          role="img"
          aria-label={`${etiqueta}: ${valor}`}
        />
      </div>
    </li>
  )
}

function EstadisticasEstados({ datos }: { datos: DashboardEmergencias }) {
  const estados = Object.entries(datos.conteos_por_estado).sort(([estadoA], [estadoB]) => {
    const posicionA = ORDEN_ESTADOS.indexOf(estadoA)
    const posicionB = ORDEN_ESTADOS.indexOf(estadoB)
    const ordenA = posicionA === -1 ? ORDEN_ESTADOS.length : posicionA
    const ordenB = posicionB === -1 ? ORDEN_ESTADOS.length : posicionB
    return ordenA - ordenB
  })

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-estados">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="titulo-estados" className="text-lg font-bold text-cyan-400">Emergencias por estado</h2>
        <span className="text-xs text-slate-500">Proporción sobre el total</span>
      </div>
      {estados.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No hay conteos de estados para mostrar.</p>
      ) : (
        <>
          <ul className="mt-5 flex flex-col gap-4" aria-label="Gráfico proporcional por estado">
            {estados.map(([estado, cantidad]) => (
              <BarraHorizontal key={estado} etiqueta={etiquetaDeEstado(estado)} valor={cantidad} maximo={datos.total} />
            ))}
          </ul>
          <table className="sr-only">
            <caption>Resumen accesible de emergencias por estado</caption>
            <thead><tr><th scope="col">Estado</th><th scope="col">Cantidad</th></tr></thead>
            <tbody>
              {estados.map(([estado, cantidad]) => (
                <tr key={estado}><td>{etiquetaDeEstado(estado)}</td><td>{cantidad}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function ComparativaActividad({ datos }: { datos: DashboardEmergencias }) {
  const maximo = Math.max(datos.emergencias_activas, datos.emergencias_resueltas, 1)
  const valores = [
    { etiqueta: 'Activas', valor: datos.emergencias_activas, color: 'bg-amber-400' },
    { etiqueta: 'Resueltas', valor: datos.emergencias_resueltas, color: 'bg-emerald-400' },
  ]

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-actividad">
      <h2 id="titulo-actividad" className="text-lg font-bold text-cyan-400">Activas vs. Resueltas</h2>
      <ul className="mt-5 flex flex-col gap-4" aria-label="Comparativa de emergencias activas y resueltas">
        {valores.map((item) => (
          <BarraHorizontal key={item.etiqueta} {...item} maximo={maximo} />
        ))}
      </ul>
      <table className="sr-only">
        <caption>Comparativa accesible de emergencias activas y resueltas</caption>
        <tbody>
          {valores.map((item) => (
            <tr key={item.etiqueta}><th scope="row">{item.etiqueta}</th><td>{item.valor}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function EvolucionAbiertasResueltas({ datos }: { datos: DashboardEmergencias }) {
  const puntos = datos.evolucion_abiertas_resueltas
  const ancho = 640
  const alto = 280
  const margen = { superior: 24, derecho: 20, inferior: 44, izquierdo: 42 }
  const anchoGrafico = ancho - margen.izquierdo - margen.derecho
  const altoGrafico = alto - margen.superior - margen.inferior
  const maximo = Math.max(...puntos.flatMap((punto) => [punto.abiertas, punto.resueltas]), 1)
  const posicionX = (indice: number) =>
    margen.izquierdo + (puntos.length > 1 ? indice / (puntos.length - 1) : 0.5) * anchoGrafico
  const posicionY = (valor: number) => margen.superior + altoGrafico - (valor / maximo) * altoGrafico
  const puntosAbiertas = puntos.map((punto, indice) => `${posicionX(indice)},${posicionY(punto.abiertas)}`).join(' ')
  const puntosResueltas = puntos.map((punto, indice) => `${posicionX(indice)},${posicionY(punto.resueltas)}`).join(' ')

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-evolucion">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="titulo-evolucion" className="text-lg font-bold text-cyan-400">Evolución de abiertas y resueltas</h2>
        <div className="flex gap-4 text-xs" aria-label="Referencias del gráfico">
          <span className="text-amber-300">● Abiertas</span>
          <span className="text-emerald-300">● Resueltas</span>
        </div>
      </div>
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
              <desc id="descripcion-evolucion">Líneas superpuestas que muestran la evolución temporal de emergencias abiertas y resueltas.</desc>
              <line x1={margen.izquierdo} y1={margen.superior} x2={margen.izquierdo} y2={alto - margen.inferior} className="stroke-slate-500" />
              <line x1={margen.izquierdo} y1={alto - margen.inferior} x2={ancho - margen.derecho} y2={alto - margen.inferior} className="stroke-slate-500" />
              <text x={margen.izquierdo - 8} y={margen.superior + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{maximo}</text>
              <text x={margen.izquierdo - 8} y={alto - margen.inferior + 4} textAnchor="end" className="fill-slate-400 text-[11px]">0</text>
              <polyline points={puntosAbiertas} fill="none" className="stroke-amber-300" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points={puntosResueltas} fill="none" className="stroke-emerald-300" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              {puntos.map((punto, indice) => (
                <g key={punto.fecha}>
                  <circle cx={posicionX(indice)} cy={posicionY(punto.abiertas)} r="4" className="fill-amber-300" />
                  <circle cx={posicionX(indice)} cy={posicionY(punto.resueltas)} r="4" className="fill-emerald-300" />
                  <text x={posicionX(indice)} y={alto - margen.inferior + 24} textAnchor="middle" className="fill-slate-400 text-[10px]">{punto.fecha}</text>
                </g>
              ))}
            </svg>
          </div>
          <table className="sr-only">
            <caption>Datos accesibles de la evolución de emergencias</caption>
            <thead><tr><th scope="col">Fecha</th><th scope="col">Abiertas</th><th scope="col">Resueltas</th></tr></thead>
            <tbody>
              {puntos.map((punto) => (
                <tr key={punto.fecha}><td>{punto.fecha}</td><td>{punto.abiertas}</td><td>{punto.resueltas}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function RankingOngs({ datos }: { datos: DashboardEmergencias }) {
  const ranking = datos.ranking_ongs
  const maximo = Math.max(...ranking.map((ong) => ong.cantidad_capacidades_asignadas), 1)

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-ongs">
      <h2 id="titulo-ongs" className="text-lg font-bold text-cyan-400">Ranking de ONGs</h2>
      {ranking.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No hay capacidades asignadas para mostrar.</p>
      ) : (
        <>
          <ol className="mt-5 flex flex-col gap-4" aria-label="Ranking horizontal de ONGs por capacidades asignadas">
            {ranking.map((ong) => (
              <BarraHorizontal
                key={ong.organizacion_id}
                etiqueta={ong.organizacion_nombre}
                valor={ong.cantidad_capacidades_asignadas}
                maximo={maximo}
                color="bg-blue-400"
              />
            ))}
          </ol>
          <table className="sr-only">
            <caption>Resumen accesible del ranking de ONGs</caption>
            <thead><tr><th scope="col">ONG</th><th scope="col">Capacidades asignadas</th></tr></thead>
            <tbody>
              {ranking.map((ong) => (
                <tr key={ong.organizacion_id}><td>{ong.organizacion_nombre}</td><td>{ong.cantidad_capacidades_asignadas}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function NecesidadesActuales({ datos }: { datos: DashboardEmergencias }) {
  const necesidades = datos.necesidades_actuales
    .map((necesidad) => [necesidad.tipo_recurso, necesidad.cantidad_requerida] as const)
    .sort(([, cantidadA], [, cantidadB]) => cantidadB - cantidadA)
  const maximo = Math.max(...necesidades.map(([, cantidad]) => cantidad), 1)

  function etiquetaDeNecesidad(tipo: string): string {
    return tipo.replace(/[_-]+/g, ' ').replace(/^\p{L}/u, (letra) => letra.toUpperCase())
  }

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-necesidades">
      <h2 id="titulo-necesidades" className="text-lg font-bold text-cyan-400">Necesidades actuales</h2>
      {necesidades.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No hay necesidades actuales para mostrar.</p>
      ) : (
        <>
          <ul className="mt-5 flex flex-col gap-4" aria-label="Gráfico de necesidades actuales agrupadas por tipo">
            {necesidades.map(([tipo, cantidad]) => (
              <BarraHorizontal
                key={tipo}
                etiqueta={etiquetaDeNecesidad(tipo)}
                valor={cantidad}
                maximo={maximo}
                color="bg-fuchsia-400"
              />
            ))}
          </ul>
          <table className="sr-only">
            <caption>Resumen accesible de necesidades actuales por tipo</caption>
            <thead><tr><th scope="col">Tipo de necesidad</th><th scope="col">Cantidad</th></tr></thead>
            <tbody>
              {necesidades.map(([tipo, cantidad]) => (
                <tr key={tipo}><td>{etiquetaDeNecesidad(tipo)}</td><td>{cantidad}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function ParticipacionConsorcios({ datos }: { datos: DashboardEmergencias }) {
  const participacion = datos.participacion_consorcios
  const porcentaje = Math.min(Math.max(participacion.porcentaje_consorcios, 0), 100)

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-consorcios">
      <h2 id="titulo-consorcios" className="text-lg font-bold text-cyan-400">Participación de consorcios</h2>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-slate-900/70 p-3">
          <p className="text-xs text-slate-400">Ofertas adjudicadas</p>
          <p className="mt-1 text-2xl font-bold text-white">{numero(participacion.total_ofertas_adjudicadas)}</p>
        </div>
        <div className="rounded-lg bg-slate-900/70 p-3">
          <p className="text-xs text-slate-400">Conjuntas adjudicadas</p>
          <p className="mt-1 text-2xl font-bold text-white">{numero(participacion.ofertas_conjuntas_adjudicadas)}</p>
        </div>
        <div className="rounded-lg bg-slate-900/70 p-3">
          <p className="text-xs text-slate-400">Participación</p>
          <p className="mt-1 text-2xl font-bold text-fuchsia-300">{decimal(participacion.porcentaje_consorcios)}%</p>
        </div>
      </div>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-700" aria-label={`Participación de consorcios: ${decimal(participacion.porcentaje_consorcios)}%`} role="img">
        <div className="h-full rounded-full bg-fuchsia-400" style={{ width: `${porcentaje}%` }} />
      </div>
    </section>
  )
}

function RecursosAdjudicadosPorMes({ datos }: { datos: DashboardEmergencias }) {
  const recursos = datos.recursos_adjudicados_por_mes
  const maximo = Math.max(...recursos.map((recurso) => recurso.cantidad_adjudicada), 1)

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-adjudicados-mes">
      <h2 id="titulo-adjudicados-mes" className="text-lg font-bold text-cyan-400">Recursos adjudicados por mes</h2>
      {recursos.length === 0 ? <p className="mt-4 text-sm text-slate-400">No hay recursos adjudicados para mostrar.</p> : (
        <>
          <ul className="mt-5 flex flex-col gap-4" aria-label="Recursos adjudicados agrupados por mes y tipo">
            {recursos.map((recurso: RecursoAdjudicadoPorMes) => (
              <BarraHorizontal
                key={`${recurso.mes}-${recurso.tipo_recurso}-${recurso.tipo_recurso_id ?? 'sin-id'}`}
                etiqueta={`${recurso.mes} · ${recurso.tipo_recurso}`}
                valor={recurso.cantidad_adjudicada}
                maximo={maximo}
                color="bg-emerald-400"
              />
            ))}
          </ul>
          <table className="sr-only"><caption>Recursos adjudicados por mes y tipo</caption><thead><tr><th>Mes</th><th>Recurso</th><th>Cantidad</th></tr></thead><tbody>
            {recursos.map((recurso) => <tr key={`${recurso.mes}-${recurso.tipo_recurso}-${recurso.tipo_recurso_id ?? 'sin-id'}`}><td>{recurso.mes}</td><td>{recurso.tipo_recurso}</td><td>{numero(recurso.cantidad_adjudicada)}</td></tr>)}
          </tbody></table>
        </>
      )}
    </section>
  )
}

function DemandaVsOferta({ datos }: { datos: DashboardEmergencias }) {
  const recursos = datos.demanda_vs_oferta_por_recurso
  const maximo = Math.max(...recursos.flatMap((recurso) => [recurso.cantidad_requerida, recurso.cantidad_ofrecida]), 1)

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-demanda-oferta">
      <h2 id="titulo-demanda-oferta" className="text-lg font-bold text-cyan-400">Demanda vs. oferta por recurso</h2>
      {recursos.length === 0 ? <p className="mt-4 text-sm text-slate-400">No hay datos de demanda y oferta para mostrar.</p> : (
        <>
          <div className="mt-4 flex gap-4 text-xs"><span className="text-amber-300">● Demanda</span><span className="text-cyan-300">● Oferta</span></div>
          <ul className="mt-5 flex flex-col gap-5" aria-label="Comparación de demanda y oferta por recurso">
            {recursos.map((recurso: DemandaVsOfertaPorRecurso) => (
              <li key={`${recurso.tipo_recurso}-${recurso.tipo_recurso_id ?? 'sin-id'}`}>
                <div className="flex justify-between gap-3 text-sm"><span className="font-medium text-slate-200">{recurso.tipo_recurso}</span><span className="font-mono text-slate-300">{numero(recurso.cantidad_requerida)} / {numero(recurso.cantidad_ofrecida)}</span></div>
                <div className="mt-2 flex flex-col gap-1"><div className="h-2 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-amber-400" style={{ width: `${(recurso.cantidad_requerida / maximo) * 100}%` }} /></div><div className="h-2 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-cyan-400" style={{ width: `${(recurso.cantidad_ofrecida / maximo) * 100}%` }} /></div></div>
              </li>
            ))}
          </ul>
          <table className="sr-only"><caption>Demanda y oferta por recurso</caption><thead><tr><th>Recurso</th><th>Demanda</th><th>Oferta</th></tr></thead><tbody>
            {recursos.map((recurso) => <tr key={`${recurso.tipo_recurso}-${recurso.tipo_recurso_id ?? 'sin-id'}`}><td>{recurso.tipo_recurso}</td><td>{numero(recurso.cantidad_requerida)}</td><td>{numero(recurso.cantidad_ofrecida)}</td></tr>)}
          </tbody></table>
        </>
      )}
    </section>
  )
}

function EmergenciasPorEstadoYGravedad({ datos }: { datos: DashboardEmergencias }) {
  const filas = datos.emergencias_por_estado_y_gravedad
  const estados = Array.from(new Set(filas.map((fila) => fila.estado))).sort((a, b) => ORDEN_ESTADOS.indexOf(a) - ORDEN_ESTADOS.indexOf(b))
  const gravedades = ['baja', 'media', 'alta', 'critica']
  const cantidad = (estado: string, gravedad: string) => filas.find((fila) => fila.estado === estado && fila.nivel_gravedad === gravedad)?.cantidad ?? 0

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-estado-gravedad">
      <h2 id="titulo-estado-gravedad" className="text-lg font-bold text-cyan-400">Emergencias por estado y gravedad</h2>
      {filas.length === 0 ? <p className="mt-4 text-sm text-slate-400">No hay datos de estado y gravedad para mostrar.</p> : (
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><caption className="sr-only">Cantidad de emergencias por estado y nivel de gravedad</caption><thead><tr className="border-b border-slate-700 text-slate-400"><th className="px-3 py-2">Estado</th>{gravedades.map((gravedad) => <th key={gravedad} className="px-3 py-2 text-right">{etiquetaDeGravedad(gravedad)}</th>)}</tr></thead><tbody>
          {estados.map((estado) => <tr key={estado} className="border-b border-slate-800"><th scope="row" className="px-3 py-3 font-medium text-slate-200">{etiquetaDeEstado(estado)}</th>{gravedades.map((gravedad) => <td key={gravedad} className="px-3 py-3 text-right font-mono text-cyan-300">{cantidad(estado, gravedad)}</td>)}</tr>)}
        </tbody></table></div>
      )}
    </section>
  )
}

export function DashboardEmergencias({ datos }: DashboardEmergenciasProps) {
  const prioridadPromedio = datos.prioridad_abiertas.cantidad_emergencias > 0
    ? datos.prioridad_abiertas.promedio_prioridad.toFixed(2)
    : '—'

  return (
    <section className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Emergencias totales</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">{datos.total}</p>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Necesidades totales</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">{datos.cantidad_total_necesidades}</p>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Tiempo medio de vida</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">{datos.tiempo_medio_vida_horas.toFixed(2)} h</p>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Prioridad promedio de abiertas</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">{prioridadPromedio}</p>
        </div>
      </div>

      <div className="grid gap-4">
        <ComparativaActividad datos={datos} />
        <EvolucionAbiertasResueltas datos={datos} />
      </div>

      <NecesidadesActuales datos={datos} />

      <div className="grid gap-4 lg:grid-cols-2">
        <ParticipacionConsorcios datos={datos} />
        <RecursosAdjudicadosPorMes datos={datos} />
      </div>

      <DemandaVsOferta datos={datos} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <EmergenciasPorEstadoYGravedad datos={datos} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RankingOngs datos={datos} />
        <EstadisticasEstados datos={datos} />
      </div>

      {datos.emergencias.length === 0 ? (
        <p className="rounded-xl border border-slate-700 bg-slate-800 p-6 text-sm text-slate-400 shadow-2xl">
          Todavía no hay emergencias registradas.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {datos.emergencias.map((emergencia) => (
            <EmergenciaResumen key={emergencia.id} emergencia={emergencia} />
          ))}
        </ul>
      )}
    </section>
  )
}
