import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, registrar } from '../services'
import type { RegistroRequest, RolUsuario } from '../types'

const ROLES: RolUsuario[] = [
  'OPERADOR_MUNICIPAL',
  'CENTRO_COORDINADOR',
  'REPRESENTANTE_ONG',
]

const ETIQUETAS_ROL: Record<RolUsuario, string> = {
  OPERADOR_MUNICIPAL: 'Operador municipal',
  CENTRO_COORDINADOR: 'Centro coordinador',
  REPRESENTANTE_ONG: 'Representante de ONG',
}

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

function esEmailValido(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return 'Ese email ya está registrado. Probá iniciar sesión.'
    }
    if (error.status === 400) {
      return `La contraseña es demasiado larga (máximo 72 bytes). ${error.detail}`
    }
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    if (error.status === 403) {
      return `Tu usuario está inactivo. ${error.detail}`
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function RegistroPage({ onIrALogin }: { onIrALogin: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rol, setRol] = useState<RolUsuario>('OPERADOR_MUNICIPAL')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

    if (!email.trim()) {
      setError('Ingresá tu email.')
      return
    }
    if (!esEmailValido(email.trim())) {
      setError('Ingresá un email válido.')
      return
    }
    if (!password) {
      setError('Ingresá tu contraseña.')
      return
    }
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.')
      return
    }

    setEnviando(true)
    try {
      const datos: RegistroRequest = { email: email.trim(), password, rol }
      await registrar(datos)
      setPassword('')
      onIrALogin()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
      <h2 className="text-xl font-bold text-cyan-400 mb-1">Crear cuenta</h2>
      <p className="text-sm text-slate-400 mb-5">
        Registrate para poder coordinar operaciones de rescate.
      </p>

      <form onSubmit={manejarEnvio} className="flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="registro-email" className={claseEtiqueta}>
            Email
          </label>
          <input
            id="registro-email"
            type="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
            placeholder="operador@rescuesync.com"
            autoComplete="email"
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-password" className={claseEtiqueta}>
            Contraseña
          </label>
          <input
            id="registro-password"
            type="password"
            value={password}
            onChange={(evento) => setPassword(evento.target.value)}
            placeholder="Mínimo 8 caracteres"
            autoComplete="new-password"
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-rol" className={claseEtiqueta}>
            Rol
          </label>
          <select
            id="registro-rol"
            value={rol}
            onChange={(evento) => setRol(evento.target.value as RolUsuario)}
            className={claseCampo}
          >
            {ROLES.map((valor) => (
              <option key={valor} value={valor}>
                {ETIQUETAS_ROL[valor]}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={enviando}
          className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enviando ? 'Registrando...' : 'Registrarme'}
        </button>
      </form>

      <button
        type="button"
        onClick={onIrALogin}
        className="mt-4 w-full text-sm text-sky-400 hover:underline"
      >
        ¿Ya tenés cuenta? Iniciá sesión
      </button>
    </section>
  )
}
