import { useEffect, useState } from 'react'
import { ApiError, listarBandejaEmergencias } from '../services'
import type {
  BandaEmergencias,
  EstadoEmergencia,
  EmergenciaRead,
  NivelGravedad,
} from '../types'

const NIVELES_GRAVEDAD: { valor: NivelGravedad; etiqueta: string }[] = [
  { valor: 'baja', etiqueta: 'Baja' },
  { valor: 'media', etiqueta: 'Media' },
  { valor: 'alta', etiqueta: 'Alta' },
  { valor: 'critica', etiqueta: 'Crítica' },
]

const ESTADOS_EMERGENCIA: { valor: EstadoEmergencia; etiqueta: string }[] = [
  { valor: 'esperando_lotes', etiqueta: 'Esperando lotes' },
  { valor: 'esperando_ofertas', etiqueta: 'Esperando ofertas' },
  { valor: 'en_proceso', etiqueta: 'En proceso' },
  { valor: 'resuelta', etiqueta: 'Resuelta' },
]

const POR_PAGINA = 10

const claseError =
  'rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300'

function etiquetaDeGravedad(nivel: NivelGravedad): string {
  return NIVELES_GRAVEDAD.find((opcion) => opcion.valor === nivel)?.etiqueta ?? nivel
}

const CLASES_GRAVEDAD: Record<NivelGravedad, string> = {
  baja: 'rounded-full border border-emerald-500/50 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300',
  media: 'rounded-full border border-yellow-500/50 bg-yellow-500/10 px-2 py-0.5 text-xs text-yellow-300',
  alta: 'rounded-full border border-orange-500/50 bg-orange-500/10 px-2 py-0.5 text-xs text-orange-300',
  critica: 'rounded-full border border-red-500/50 bg-red-500/10 px-2 py-0.5 text-xs text-red-300',
}

function clasesDeGravedad(nivel: NivelGravedad): string {
  return CLASES_GRAVEDAD[nivel]
}

function etiquetaDeEstado(estado: EstadoEmergencia | null): string {
  if (estado === null) {
    return 'Sin estado'
  }
  return ESTADOS_EMERGENCIA.find((opcion) => opcion.valor === estado)?.etiqueta ?? estado
}

function formatearFecha(valor: string | null, sinDato: string): string {
  if (valor === null) {
    return sinDato
  }
  const fecha = new Date(valor)
  return Number.isNaN(fecha.getTime()) ? valor : fecha.toLocaleString('es-AR')
}

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

function idPanel(emergenciaId: number): string {
  return `detalle-emergencia-${emergenciaId}`
}

function DetalleEmergencia({ emergencia }: { emergencia: EmergenciaRead }) {
  return (
    <div
      id={idPanel(emergencia.id)}
      className="rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm"
    >
      <dl className="flex flex-col">
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Id</dt>
          <dd className="font-mono text-cyan-400">{emergencia.id}</dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Nivel de gravedad</dt>
          <dd className="font-mono text-cyan-400">
            {etiquetaDeGravedad(emergencia.nivel_gravedad)}
          </dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Zona afectada</dt>
          <dd className="font-mono text-cyan-400 break-all">
            {emergencia.zona_afectada}
          </dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Estado</dt>
          <dd className="font-mono text-cyan-400">
            {etiquetaDeEstado(emergencia.estado)}
          </dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Registrada el</dt>
          <dd className="font-mono text-cyan-400">
            {formatearFecha(emergencia.fecha_hora_registro, 'Sin fecha')}
          </dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Publicada</dt>
          <dd className="font-mono text-cyan-400">
            {emergencia.publicada ? 'Sí' : 'No publicada'}
          </dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Fecha de publicación</dt>
          <dd className="font-mono text-cyan-400">
            {formatearFecha(emergencia.fecha_publicacion, 'No publicada')}
          </dd>
        </div>
        {emergencia.bonita_case_id !== null && (
          <div className="flex justify-between gap-4 py-1">
            <dt className="text-slate-400">Caso Bonita</dt>
            <dd className="font-mono text-cyan-400 break-all">
              {emergencia.bonita_case_id}
            </dd>
          </div>
        )}
      </dl>

      <div className="mt-4 border-t border-slate-700 pt-3">
        <p className="text-xs font-semibold text-slate-400">Descripción inicial</p>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
          {emergencia.descripcion_inicial}
        </p>
      </div>
    </div>
  )
}

export function EmergenciasPage() {
  const [pagina, setPagina] = useState(1)
  const [bandeja, setBandeja] = useState<BandaEmergencias | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())

  useEffect(() => {
    let vigente = true

    async function cargar() {
      setCargando(true)
      setError(null)
      try {
        const datos = await listarBandejaEmergencias({
          publicada: false,
          pagina,
          por_pagina: POR_PAGINA,
        })
        if (!vigente) {
          return
        }
        setBandeja(datos)
        if (datos.paginas > 0 && datos.pagina > datos.paginas) {
          setPagina(datos.paginas)
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
  }, [pagina])

  function alternar(emergenciaId: number) {
    setDesplegadas((actuales) => {
      const siguientes = new Set(actuales)
      if (siguientes.has(emergenciaId)) {
        siguientes.delete(emergenciaId)
      } else {
        siguientes.add(emergenciaId)
      }
      return siguientes
    })
  }

  const totalPaginas = bandeja?.paginas ?? 0
  const paginaActual = bandeja?.pagina ?? pagina
  const sinPaginas = totalPaginas === 0

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <p className="text-sm text-slate-400">
          Emergencias sin publicar. Tocá una fila para ver su detalle.
        </p>
      </div>

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando emergencias...
        </p>
      )}

      {!cargando && error !== null && (
        <p role="alert" className={claseError}>
          No se pudieron cargar las emergencias. {error}
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Todavía no hay emergencias registradas.
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {bandeja.items.map((emergencia) => {
            const desplegada = desplegadas.has(emergencia.id)

            return (
              <li
                key={emergencia.id}
                className="group rounded-xl bg-slate-800 border border-slate-700 shadow-2xl transition hover:border-cyan-400"
              >
                <button
                  type="button"
                  onClick={() => alternar(emergencia.id)}
                  aria-expanded={desplegada}
                  aria-controls={idPanel(emergencia.id)}
                  className="flex w-full flex-col gap-3 p-4 text-left"
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-base font-semibold text-white">
                      {emergencia.zona_afectada}
                    </span>
                    <span className="font-mono text-xs text-slate-500">
                      #{emergencia.id}
                    </span>
                  </span>

                  <span className="flex flex-wrap gap-2">
                    <span
                      className={clasesDeGravedad(emergencia.nivel_gravedad)}
                    >
                      Gravedad: {etiquetaDeGravedad(emergencia.nivel_gravedad)}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                      Estado: {etiquetaDeEstado(emergencia.estado)}
                    </span>
                  </span>

                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-xs text-slate-400">
                      Registrada el{' '}
                      {formatearFecha(emergencia.fecha_hora_registro, 'Sin fecha')}
                    </span>
                    <span className="text-xs font-semibold text-cyan-400">
                      {desplegada ? 'Ocultar detalles ▾' : 'Ver detalles ▸'}
                    </span>
                  </span>
                </button>

                {desplegada && (
                  <div className="px-4 pb-4">
                    <DetalleEmergencia emergencia={emergencia} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!sinPaginas && (
        <nav
          aria-label="Paginación de emergencias"
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <button
            type="button"
            onClick={() => setPagina((actual) => Math.max(1, actual - 1))}
            disabled={cargando || paginaActual <= 1}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Anterior
          </button>

          <p className="text-sm text-slate-400">
            Página {paginaActual} de {totalPaginas}
          </p>

          <button
            type="button"
            onClick={() => setPagina((actual) => actual + 1)}
            disabled={cargando || paginaActual >= totalPaginas}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Siguiente
          </button>
        </nav>
      )}
    </section>
  )
}
