import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { ApiError, listarOrganizaciones, listarRoles, registrar } from '../services'
import type { Organizacion, RegistroRequest, Rol } from '../types'

const ETIQUETAS_ROL: Record<string, string> = {
  OPERADOR_MUNICIPAL: 'Operador municipal',
  CENTRO_COORDINADOR: 'Centro coordinador',
  REPRESENTANTE_ONG: 'Representante de ONG',
  DIRECTOR_AUDITOR: 'Director/Auditor',
}

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

const claseAviso =
  'rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm text-amber-300'

function nombreDeRol(rol: Rol): string {
  return ETIQUETAS_ROL[rol.nombre] ?? rol.nombre
}

function esEmailValido(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function describirError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return error.detail
    }
    if (error.status === 409) {
      return 'Ese email ya está registrado.'
    }
    if (error.status === 400) {
      return error.detail
    }
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

export function RegistroPage({ onVolver }: { onVolver: () => void }) {
  const [nombre, setNombre] = useState('')
  const [apellido, setApellido] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [roles, setRoles] = useState<Rol[]>([])
  const [rolId, setRolId] = useState<number | ''>('')
  const [organizaciones, setOrganizaciones] = useState<Organizacion[]>([])
  const [organizacionId, setOrganizacionId] = useState<number | ''>('')
  const [exito, setExito] = useState<string | null>(null)
  const esRepresentante = roles.find((rol) => rol.id === rolId)?.nombre === 'REPRESENTANTE_ONG'
  const [cargandoRoles, setCargandoRoles] = useState(true)
  const [errorRoles, setErrorRoles] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const formularioVigente = useRef(false)

  useEffect(() => {
    formularioVigente.current = true
    return () => {
      formularioVigente.current = false
    }
  }, [])

  useEffect(() => {
    let vigente = true

    async function cargarRoles() {
      setCargandoRoles(true)
      setErrorRoles(null)
      try {
        const [datos, organizacionesDisponibles] = await Promise.all([
          listarRoles(), listarOrganizaciones(),
        ])
        if (!vigente) return
        setRoles(datos)
        setOrganizaciones(organizacionesDisponibles)
        setRolId(datos.length > 0 ? datos[0].id : '')
      } catch (fallo) {
        if (!vigente) return
        setRoles([])
        setErrorRoles(
          fallo instanceof ApiError
            ? fallo.detail
            : 'No se pudieron cargar los roles y las organizaciones disponibles.',
        )
      } finally {
        if (vigente) setCargandoRoles(false)
      }
    }

    void cargarRoles()

    return () => {
      vigente = false
    }
  }, [])

  function manejarNombre(evento: ChangeEvent<HTMLInputElement>) {
    setNombre(evento.target.value)
  }

  function manejarApellido(evento: ChangeEvent<HTMLInputElement>) {
    setApellido(evento.target.value)
  }

  function manejarEmail(evento: ChangeEvent<HTMLInputElement>) {
    setEmail(evento.target.value)
  }

  function manejarPassword(evento: ChangeEvent<HTMLInputElement>) {
    setPassword(evento.target.value)
  }

  function manejarRol(evento: ChangeEvent<HTMLSelectElement>) {
    setRolId(Number(evento.target.value))
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)
    setExito(null)

    if (nombre.trim().length < 2) {
      setError('Ingresá tu nombre (mínimo 2 caracteres).')
      return
    }
    if (apellido.trim().length < 2) {
      setError('Ingresá tu apellido (mínimo 2 caracteres).')
      return
    }
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
    if (rolId === '') {
      setError('Seleccioná un rol.')
      return
    }
    if (esRepresentante && organizacionId === '') {
      setError('Seleccioná la organización del representante de ONG.')
      return
    }

    setEnviando(true)
    try {
      const datos: RegistroRequest = {
        email: email.trim(),
        password,
        nombre: nombre.trim(),
        apellido: apellido.trim(),
        rol_id: rolId,
        organizacion_id: organizacionId === '' ? null : organizacionId,
      }
      await registrar(datos)
      if (!formularioVigente.current) return
      setPassword('')
      setNombre('')
      setApellido('')
      setEmail('')
      setExito('Usuario creado. Tu sesión de coordinador sigue activa; podés crear otro usuario o volver a la bandeja.')
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  const rolesInhabilitados = cargandoRoles || errorRoles !== null

  return (
    <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
      <h2 className="text-xl font-bold text-cyan-400 mb-1">Crear usuario</h2>
      <p className="text-sm text-slate-400 mb-5">
        Asigná el rol y la organización de la nueva cuenta.
      </p>

      <form onSubmit={manejarEnvio} className="flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="registro-nombre" className={claseEtiqueta}>
            Nombre
          </label>
          <input
            id="registro-nombre"
            type="text"
            value={nombre}
            onChange={manejarNombre}
            placeholder="Ana"
            minLength={2}
            maxLength={80}
            required
            autoComplete="given-name"
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-apellido" className={claseEtiqueta}>
            Apellido
          </label>
          <input
            id="registro-apellido"
            type="text"
            value={apellido}
            onChange={manejarApellido}
            placeholder="Gómez"
            minLength={2}
            maxLength={80}
            required
            autoComplete="family-name"
            className={claseCampo}
          />
        </div>

        <div>
          <label htmlFor="registro-email" className={claseEtiqueta}>
            Email
          </label>
          <input
            id="registro-email"
            type="email"
            value={email}
            onChange={manejarEmail}
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
            onChange={manejarPassword}
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
            value={rolId}
            onChange={manejarRol}
            disabled={rolesInhabilitados}
            className={claseCampo}
          >
            {cargandoRoles && <option value="">Cargando roles...</option>}
            {roles.map((rol) => (
              <option key={rol.id} value={rol.id}>
                {nombreDeRol(rol)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="registro-organizacion" className={claseEtiqueta}>
            Organización {esRepresentante ? '(obligatoria)' : '(opcional)'}
          </label>
          <select id="registro-organizacion" value={organizacionId}
            onChange={(evento) => setOrganizacionId(evento.target.value === '' ? '' : Number(evento.target.value))}
            disabled={rolesInhabilitados} className={claseCampo}>
            <option value="">Sin organización</option>
            {organizaciones.map((organizacion) => (
              <option key={organizacion.id} value={organizacion.id}>{organizacion.nombre}</option>
            ))}
          </select>
          {esRepresentante && !cargandoRoles && organizaciones.length === 0 && !errorRoles && (
            <p className={claseAviso}>No hay organizaciones disponibles para asignar.</p>
          )}
        </div>

        {exito && <p role="status" className="text-sm text-emerald-300">{exito}</p>}

        {errorRoles && (
          <p role="alert" className={claseAviso}>
            {errorRoles}
          </p>
        )}

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
          disabled={enviando || rolesInhabilitados}
          className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enviando ? 'Creando usuario...' : 'Crear usuario'}
        </button>
      </form>

      <button
        type="button"
        onClick={onVolver}
        className="mt-4 w-full text-sm text-sky-400 hover:underline"
      >
        Volver a la bandeja
      </button>
    </section>
  )
}
