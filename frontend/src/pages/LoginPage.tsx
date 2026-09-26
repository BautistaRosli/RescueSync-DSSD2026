import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, iniciarSesion } from '../services'
import type { AuthResponse, LoginRequest } from '../types'

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

function esEmailValido(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return 'Credenciales inválidas. Revisá tu email y tu contraseña.'
    }
    if (error.status === 403) {
      return 'Tu usuario está inactivo. Contactá al administrador.'
    }
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

export function LoginPage({
  onIrARegistro,
  onSesionIniciada,
}: {
  onIrARegistro: () => void
  onSesionIniciada: (sesion: AuthResponse) => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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

    setEnviando(true)
    try {
      const datos: LoginRequest = { email: email.trim(), password }
      onSesionIniciada(await iniciarSesion(datos))
      setPassword('')
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
      <h2 className="text-xl font-bold text-cyan-400 mb-1">Iniciar sesión</h2>
      <p className="text-sm text-slate-400 mb-5">
        Ingresá con tu cuenta de RescueSync.
      </p>

      <form onSubmit={manejarEnvio} className="flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="login-email" className={claseEtiqueta}>
            Email
          </label>
          <input
            id="login-email"
            type="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
            placeholder="operador@rescuesync.com"
            autoComplete="email"
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="login-password" className={claseEtiqueta}>
            Contraseña
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(evento) => setPassword(evento.target.value)}
            placeholder="Tu contraseña"
            autoComplete="current-password"
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

        <button
          type="submit"
          disabled={enviando}
          className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enviando ? 'Verificando...' : 'Entrar'}
        </button>
      </form>

      <button
        type="button"
        onClick={onIrARegistro}
        className="mt-4 w-full text-sm text-sky-400 hover:underline"
      >
        ¿No tenés cuenta? Registrate
      </button>
    </section>
  )
}
