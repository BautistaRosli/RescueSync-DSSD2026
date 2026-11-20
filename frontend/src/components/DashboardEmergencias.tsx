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
    en_proceso: 'En proceso',
    resuelta: 'Resuelta',
  }
  return etiquetas[estado] ?? estado
}

function BarraEstado({ estado, cantidad, total }: { estado: string; cantidad: number; total: number }) {
  const porcentaje = total > 0 ? (cantidad / total) * 100 : 0

  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-slate-200">{etiquetaDeEstado(estado)}</span>
        <span className="font-mono text-cyan-300">{cantidad}</span>
      </div>
      <div
        className="h-3 overflow-hidden rounded-full bg-slate-700"
        role="img"
        aria-label={`${etiquetaDeEstado(estado)}: ${cantidad} de ${total} emergencias`}
      >
        <div
          className="h-full rounded-full bg-cyan-400 transition-all"
          style={{ width: `${porcentaje}%` }}
        />
      </div>
    </li>
  )
}

function EstadisticasEstados({ datos }: { datos: DashboardEmergencias }) {
  const estados = Object.entries(datos.conteos_por_estado)

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl" aria-labelledby="titulo-estados">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="titulo-estados" className="text-lg font-bold text-cyan-400">
          Emergencias por estado
        </h2>
        <span className="text-xs text-slate-500">Proporción sobre el total</span>
      </div>

      {estados.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">No hay conteos de estados para mostrar.</p>
      ) : (
        <>
          <ul className="mt-5 flex flex-col gap-4" aria-label="Gráfico proporcional por estado">
            {estados.map(([estado, cantidad]) => (
              <BarraEstado key={estado} estado={estado} cantidad={cantidad} total={datos.total} />
            ))}
          </ul>
          <table className="sr-only">
            <caption>Resumen accesible de emergencias por estado</caption>
            <thead>
              <tr>
                <th scope="col">Estado</th>
                <th scope="col">Cantidad</th>
              </tr>
            </thead>
            <tbody>
              {estados.map(([estado, cantidad]) => (
                <tr key={estado}>
                  <td>{etiquetaDeEstado(estado)}</td>
                  <td>{cantidad}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

export function DashboardEmergencias({ datos }: DashboardEmergenciasProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Total registrado</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">{datos.total}</p>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 shadow-2xl">
          <p className="text-sm text-slate-400">Estados registrados</p>
          <p className="mt-1 text-3xl font-bold text-cyan-400">
            {Object.keys(datos.conteos_por_estado).length}
          </p>
        </div>
      </div>

      <EstadisticasEstados datos={datos} />

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
