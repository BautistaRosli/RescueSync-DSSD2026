import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, crearOrganizacion } from '../services'

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    if (error.status === 401) {
      return 'Tu sesión no es válida o venció. Cerrá sesión y volvé a ingresar.'
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function RegistroOngPage({ onVolver }: { onVolver: () => void }) {
  const [nombreOng, setNombreOng] = useState('')
  const [cuitOng, setCuitOng] = useState('')
  const [emailOng, setEmailOng] = useState('')
  const [telefonoOng, setTelefonoOng] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [exito, setExito] = useState(false)
  const [enviando, setEnviando] = useState(false)

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)
    setExito(false)

    if (nombreOng.trim().length < 2) {
      setError('Ingresá el nombre de tu organización (mínimo 2 caracteres).')
      return
    }
    if (!cuitOng.trim()) {
      setError('El CUIT de la organización es obligatorio.')
      return
    }
    if (!emailOng.trim()) {
      setError('El email de contacto de la organización es obligatorio.')
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailOng.trim())) {
      setError('El email de contacto de la organización debe ser válido.')
      return
    }

    setEnviando(true)
    try {
      await crearOrganizacion({
        nombre: nombreOng.trim(),
        tipo: 'ong',
        cuit: cuitOng.trim(),
        email: emailOng.trim(),
        telefono: telefonoOng.trim() || null,
      })
      setNombreOng('')
      setCuitOng('')
      setEmailOng('')
      setTelefonoOng('')
      setExito(true)
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
      <h2 className="text-xl font-bold text-cyan-400 mb-1">Crear ONG</h2>
      <p className="text-sm text-slate-400 mb-5">
        Datos de la organización.
      </p>

      <form onSubmit={manejarEnvio} className="flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="registro-ong-nombre" className={claseEtiqueta}>
            Nombre de la organización
          </label>
          <input
            id="registro-ong-nombre"
            type="text"
            value={nombreOng}
            onChange={(evento) => setNombreOng(evento.target.value)}
            placeholder="Cruz Verde Regional"
            minLength={2}
            maxLength={150}
            required
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-ong-cuit" className={claseEtiqueta}>
            CUIT
          </label>
          <input
            id="registro-ong-cuit"
            type="text"
            value={cuitOng}
            onChange={(evento) => setCuitOng(evento.target.value)}
            required
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-ong-email" className={claseEtiqueta}>
            Email de contacto
          </label>
          <input
            id="registro-ong-email"
            type="email"
            value={emailOng}
            onChange={(evento) => setEmailOng(evento.target.value)}
            placeholder="contacto@cruzverde.org"
            maxLength={150}
            required
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-ong-telefono" className={claseEtiqueta}>
            Teléfono
          </label>
          <input
            id="registro-ong-telefono"
            type="text"
            value={telefonoOng}
            onChange={(evento) => setTelefonoOng(evento.target.value)}
            placeholder="221 555-0000"
            maxLength={50}
            className={claseCampo}
          />
        </div>

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300"
          >
            {error}
          </p>
        )}

        {exito && (
          <p role="status" className="text-sm text-emerald-400">
            ONG creada correctamente.
          </p>
        )}

        <button
          type="submit"
          disabled={enviando}
          className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enviando ? 'Creando ONG...' : 'Crear ONG'}
        </button>
      </form>

      <button
        type="button"
        onClick={onVolver}
        className="mt-4 w-full text-sm text-sky-400 hover:underline"
      >
        Volver
      </button>
    </section>
  )
}
