import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { ApiError, registrarEmergencia } from '../services'
import type {
  AuthResponse,
  EmergenciaCreateRequest,
  EmergenciaCreada,
  NivelGravedad,
} from '../types'

const NIVELES_GRAVEDAD: { valor: NivelGravedad; etiqueta: string }[] = [
  { valor: 'baja', etiqueta: 'Baja' },
  { valor: 'media', etiqueta: 'Media' },
  { valor: 'alta', etiqueta: 'Alta' },
  { valor: 'critica', etiqueta: 'Crítica' },
]

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

const claseError =
  'rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300'

function etiquetaDeGravedad(nivel: NivelGravedad): string {
  return NIVELES_GRAVEDAD.find((opcion) => opcion.valor === nivel)?.etiqueta ?? nivel
}

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function RegistrarEmergenciaPage({ sesion }: { sesion: AuthResponse }) {
  const [nivelGravedad, setNivelGravedad] = useState<NivelGravedad>('media')
  const [zona, setZona] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [creada, setCreada] = useState<EmergenciaCreada | null>(null)

  function manejarGravedad(evento: ChangeEvent<HTMLSelectElement>) {
    setNivelGravedad(evento.target.value as NivelGravedad)
  }

  function manejarZona(evento: ChangeEvent<HTMLInputElement>) {
    setZona(evento.target.value)
  }

  function manejarDescripcion(evento: ChangeEvent<HTMLTextAreaElement>) {
    setDescripcion(evento.target.value)
  }

  function registrarOtra() {
    setCreada(null)
    setNivelGravedad('media')
    setZona('')
    setDescripcion('')
    setError(null)
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

    if (!nivelGravedad) {
      setError('Seleccioná un nivel de gravedad.')
      return
    }
    if (!zona.trim()) {
      setError('Ingresá la zona afectada.')
      return
    }
    if (!descripcion.trim()) {
      setError('Ingresá la descripción inicial.')
      return
    }

    setEnviando(true)
    try {
      const datos: EmergenciaCreateRequest = {
        nivel_gravedad: nivelGravedad,
        zona_afectada: zona.trim(),
        descripcion_inicial: descripcion.trim(),
      }
      setCreada(await registrarEmergencia(datos))
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  const fechaRegistro = creada
    ? new Date(creada.fecha_hora_registro).toLocaleString('es-AR')
    : ''

  return (
    <section className="flex flex-col gap-6">
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">Operador municipal</h2>
        <p className="text-sm text-slate-400 mb-5">
          Sesión activa. Registrá una emergencia del desastre.
        </p>

        <dl className="rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm">
          <div className="flex justify-between gap-4 py-1">
            <dt className="text-slate-400">Email</dt>
            <dd className="font-mono text-cyan-400 break-all">{sesion.usuario.email}</dd>
          </div>
          <div className="flex justify-between gap-4 py-1">
            <dt className="text-slate-400">Nombre</dt>
            <dd className="font-mono text-cyan-400">
              {sesion.usuario.nombre} {sesion.usuario.apellido}
            </dd>
          </div>
          <div className="flex justify-between gap-4 py-1">
            <dt className="text-slate-400">Rol</dt>
            <dd className="font-mono text-cyan-400">{sesion.rol}</dd>
          </div>
        </dl>
      </div>

      {creada ? (
        <div className="rounded-xl bg-slate-800 border border-emerald-500/40 p-6 shadow-2xl">
          <h2 className="text-xl font-bold text-emerald-400 mb-1">
            Emergencia registrada
          </h2>
          <p className="text-sm text-slate-400 mb-5">
            La emergencia quedó registrada y pendiente de publicación.
          </p>

          <dl className="rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm">
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Id</dt>
              <dd className="font-mono text-cyan-400">{creada.id}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Nivel de gravedad</dt>
              <dd className="font-mono text-cyan-400">
                {etiquetaDeGravedad(creada.nivel_gravedad)}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Zona afectada</dt>
              <dd className="font-mono text-cyan-400 break-all">{creada.zona_afectada}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Registrada el</dt>
              <dd className="font-mono text-cyan-400">{fechaRegistro}</dd>
            </div>
          </dl>

          <button
            type="button"
            onClick={registrarOtra}
            className="mt-4 w-full rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400"
          >
            Registrar otra emergencia
          </button>
        </div>
      ) : (
        <form
          onSubmit={manejarEnvio}
          className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl flex flex-col gap-4"
          noValidate
        >
          <h3 className="text-lg font-bold text-cyan-400">Registrar emergencia</h3>

          <div>
            <label htmlFor="emergencia-gravedad" className={claseEtiqueta}>
              Nivel de gravedad
            </label>
            <select
              id="emergencia-gravedad"
              value={nivelGravedad}
              onChange={manejarGravedad}
              className={claseCampo}
            >
              {NIVELES_GRAVEDAD.map((opcion) => (
                <option key={opcion.valor} value={opcion.valor}>
                  {opcion.etiqueta}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="emergencia-zona" className={claseEtiqueta}>
              Zona afectada
            </label>
            <input
              id="emergencia-zona"
              type="text"
              value={zona}
              onChange={manejarZona}
              placeholder="Barrio Norte, ruta 12 km 3"
              maxLength={200}
              required
              className={claseCampo}
            />
          </div>

          <div>
            <label htmlFor="emergencia-descripcion" className={claseEtiqueta}>
              Descripción inicial
            </label>
            <textarea
              id="emergencia-descripcion"
              value={descripcion}
              onChange={manejarDescripcion}
              placeholder="Contá brevemente qué está pasando."
              rows={4}
              required
              className={claseCampo}
            />
          </div>

          {error && (
            <p role="alert" className={claseError}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={enviando}
            className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {enviando ? 'Registrando...' : 'Registrar emergencia'}
          </button>
        </form>
      )}
    </section>
  )
}
