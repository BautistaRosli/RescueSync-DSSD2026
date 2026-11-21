import type { DashboardEmergencias, EmergenciaRespuesta } from '../types'

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
  const necesidadesPorTipo = new Map<string, number>()

  datos.emergencias
    .filter((emergencia) => emergencia.estado !== 'resuelta')
    .flatMap((emergencia) => emergencia.lotes)
    .forEach((necesidad) => {
      const tipo = necesidad.tipo.trim() || 'Sin tipo'
      necesidadesPorTipo.set(tipo, (necesidadesPorTipo.get(tipo) ?? 0) + necesidad.cantidad)
    })

  const necesidades = Array.from(necesidadesPorTipo.entries()).sort(([, cantidadA], [, cantidadB]) => cantidadB - cantidadA)
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

export function DashboardEmergencias({ datos }: DashboardEmergenciasProps) {
  const prioridadesAbiertas = datos.emergencias
    .filter((emergencia) => emergencia.estado !== 'resuelta' && emergencia.prioridad != null)
    .map((emergencia) => emergencia.prioridad as number)
  const prioridadPromedio = prioridadesAbiertas.length > 0
    ? (prioridadesAbiertas.reduce((suma, prioridad) => suma + prioridad, 0) / prioridadesAbiertas.length).toFixed(2)
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
