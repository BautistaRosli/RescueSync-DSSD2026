import { useEffect, useState } from 'react'
import { ApiError, listarEmergencias, obtenerEmergencia } from '../services'
import type { EstadoEmergencia, EmergenciaRead, NivelGravedad } from '../types'

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

const claseError =
  'rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300'

function etiquetaDeGravedad(nivel: NivelGravedad): string {
  return NIVELES_GRAVEDAD.find((opcion) => opcion.valor === nivel)?.etiqueta ?? nivel
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

function ListadoEmergencias({
  onVerDetalle,
}: {
  onVerDetalle: (emergenciaId: number) => void
}) {
  const [emergencias, setEmergencias] = useState<EmergenciaRead[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const datos = await listarEmergencias()
        if (vigente) {
          setEmergencias(datos)
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
  }, [])

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">Emergencias</h2>
        <p className="text-sm text-slate-400">
          Listado completo de emergencias registradas. Tocá una para ver el detalle.
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

      {!cargando && error === null && emergencias.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Todavía no hay emergencias registradas.
        </p>
      )}

      {!cargando && error === null && emergencias.length > 0 && (
        <ul className="flex flex-col gap-3">
          {emergencias.map((emergencia) => (
            <li key={emergencia.id}>
              <button
                type="button"
                onClick={() => onVerDetalle(emergencia.id)}
                className="w-full rounded-xl bg-slate-800 border border-slate-700 p-4 text-left shadow-2xl transition hover:border-cyan-400"
              >
                <span className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-base font-semibold text-white">
                    {emergencia.zona_afectada}
                  </span>
                  <span className="font-mono text-xs text-slate-500">
                    #{emergencia.id}
                  </span>
                </span>

                <span className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                    Gravedad: {etiquetaDeGravedad(emergencia.nivel_gravedad)}
                  </span>
                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                    Estado: {etiquetaDeEstado(emergencia.estado)}
                  </span>
                </span>

                <span className="mt-3 block text-xs text-slate-400">
                  Registrada el{' '}
                  {formatearFecha(emergencia.fecha_hora_registro, 'Sin fecha')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function DetalleEmergencia({
  emergenciaId,
  onVolver,
}: {
  emergenciaId: number
  onVolver: () => void
}) {
  const [emergencia, setEmergencia] = useState<EmergenciaRead | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [noEncontrada, setNoEncontrada] = useState(false)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const datos = await obtenerEmergencia(emergenciaId)
        if (vigente) {
          setEmergencia(datos)
        }
      } catch (fallo) {
        if (vigente) {
          if (fallo instanceof ApiError && fallo.status === 404) {
            setNoEncontrada(true)
          } else {
            setError(describirError(fallo))
          }
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
  }, [emergenciaId])

  const volver = (
    <button
      type="button"
      onClick={onVolver}
      className="w-full rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
    >
      Volver al listado
    </button>
  )

  if (noEncontrada) {
    return (
      <section className="flex flex-col gap-4">
        <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
          <h2 className="text-xl font-bold text-amber-400 mb-1">
            Emergencia no encontrada
          </h2>
          <p className="text-sm text-slate-400 mb-5">
            La emergencia #{emergenciaId} no existe o fue eliminada.
          </p>
          {volver}
        </div>
      </section>
    )
  }

  if (cargando) {
    return (
      <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">
          Detalle de la emergencia
        </h2>
        <p className="text-sm text-slate-400">Cargando emergencia...</p>
      </section>
    )
  }

  if (error !== null || emergencia === null) {
    return (
      <section className="flex flex-col gap-4">
        <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
          <h2 className="text-xl font-bold text-red-400 mb-1">
            No se pudo cargar la emergencia
          </h2>
          <p role="alert" className="text-sm text-slate-300 mb-5">
            {error ?? 'Ocurrió un error inesperado. Intentá de nuevo.'}
          </p>
          {volver}
        </div>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">
          Detalle de la emergencia
        </h2>
        <p className="text-sm text-slate-400 mb-5">{emergencia.zona_afectada}</p>

        <dl className="rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm">
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
            <dt className="text-slate-400">Tipo de desastre</dt>
            <dd className="font-mono text-cyan-400 break-all">
              {emergencia.tipo_desastre ?? 'Sin especificar'}
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
      </div>

      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h3 className="text-lg font-bold text-cyan-400 mb-3">
          Descripción inicial
        </h3>
        <p className="whitespace-pre-wrap text-sm text-slate-300">
          {emergencia.descripcion_inicial}
        </p>
      </div>

      {volver}
    </section>
  )
}

export function EmergenciasPage() {
  const [emergenciaId, setEmergenciaId] = useState<number | null>(null)

  if (emergenciaId === null) {
    return <ListadoEmergencias onVerDetalle={setEmergenciaId} />
  }

  return (
    <DetalleEmergencia
      emergenciaId={emergenciaId}
      onVolver={() => setEmergenciaId(null)}
    />
  )
}
