import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  ApiError,
  crearOrganizacion,
  listarOrganizaciones,
  listarRoles,
  registrar,
} from '../services'
import type { OrganizacionRead, RegistroRequest, Rol } from '../types'

const ETIQUETAS_ROL: Record<string, string> = {
  OPERADOR_MUNICIPAL: 'Operador municipal',
  CENTRO_COORDINADOR: 'Centro coordinador',
  REPRESENTANTE_ONG: 'Representante de ONG',
  DIRECTOR_AUDITOR: 'Director/Auditor',
}

const ROL_REPRESENTANTE_ONG = 'REPRESENTANTE_ONG'

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
      return 'El rol seleccionado no existe. Recargá la página.'
    }
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
  const [nombre, setNombre] = useState('')
  const [apellido, setApellido] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [roles, setRoles] = useState<Rol[]>([])
  const [rolId, setRolId] = useState<number | ''>('')
  const [cargandoRoles, setCargandoRoles] = useState(true)
  const [errorRoles, setErrorRoles] = useState<string | null>(null)
  const [organizaciones, setOrganizaciones] = useState<OrganizacionRead[]>([])
  const [organizacionId, setOrganizacionId] = useState<number | ''>('')
  const [cargandoOrganizaciones, setCargandoOrganizaciones] = useState(true)
  const [errorOrganizaciones, setErrorOrganizaciones] = useState<string | null>(
    null,
  )
  const [altaDeOng, setAltaDeOng] = useState(false)
  const [nombreOng, setNombreOng] = useState('')
  const [emailOng, setEmailOng] = useState('')
  const [telefonoOng, setTelefonoOng] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    let vigente = true

    async function cargarRoles() {
      setCargandoRoles(true)
      setErrorRoles(null)
      try {
        const datos = await listarRoles()
        if (!vigente) return
        setRoles(datos)
        setRolId(datos.length > 0 ? datos[0].id : '')
      } catch (fallo) {
        if (!vigente) return
        setRoles([])
        setErrorRoles(
          fallo instanceof ApiError
            ? fallo.detail
            : 'No se pudieron cargar los roles disponibles.',
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

  useEffect(() => {
    let vigente = true

    async function cargarOrganizaciones() {
      setCargandoOrganizaciones(true)
      setErrorOrganizaciones(null)
      try {
        const datos = await listarOrganizaciones()
        if (!vigente) return
        setOrganizaciones(datos)
      } catch (fallo) {
        if (!vigente) return
        setOrganizaciones([])
        setErrorOrganizaciones(
          fallo instanceof ApiError
            ? fallo.detail
            : 'No se pudieron cargar las organizaciones.',
        )
      } finally {
        if (vigente) setCargandoOrganizaciones(false)
      }
    }

    void cargarOrganizaciones()

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

  function manejarOrganizacion(evento: ChangeEvent<HTMLSelectElement>) {
    const valor = evento.target.value
    setOrganizacionId(valor === '' ? '' : Number(valor))
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

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
    if (esRepresentanteOng) {
      if (altaDeOng && nombreOng.trim().length < 2) {
        setError('Ingresá el nombre de tu organización (mínimo 2 caracteres).')
        return
      }
      if (!altaDeOng && organizacionId === '') {
        setError('Seleccioná tu organización o registrá una nueva.')
        return
      }
    }

    setEnviando(true)
    try {
      let organizacionElegida: number | null = esRepresentanteOng
        ? organizacionId === ''
          ? null
          : organizacionId
        : null

      if (esRepresentanteOng && altaDeOng) {
        const creada = await crearOrganizacion({
          nombre: nombreOng.trim(),
          tipo: 'ong',
          email: emailOng.trim() || null,
          telefono: telefonoOng.trim() || null,
        })
        organizacionElegida = creada.id
      }

      const datos: RegistroRequest = {
        email: email.trim(),
        password,
        nombre: nombre.trim(),
        apellido: apellido.trim(),
        rol_id: rolId,
        organizacion_id: organizacionElegida,
      }
      await registrar(datos)
      setPassword('')
      onIrALogin()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  const rolesInhabilitados = cargandoRoles || errorRoles !== null

  const esRepresentanteOng =
    roles.find((rol) => rol.id === rolId)?.nombre === ROL_REPRESENTANTE_ONG

  return (
    <section className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
      <h2 className="text-xl font-bold text-cyan-400 mb-1">Crear cuenta</h2>
      <p className="text-sm text-slate-400 mb-5">
        Registrate para poder coordinar operaciones de rescate.
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

        {esRepresentanteOng && (
          <div className="rounded-lg bg-slate-900 border border-slate-700 p-4 flex flex-col gap-4">
            <p className="text-xs text-slate-400">
              Como representante de ONG necesitás estar asociado a una
              organización para poder postular recursos.
            </p>

            {!altaDeOng && (
              <div>
                <label htmlFor="registro-organizacion" className={claseEtiqueta}>
                  Organización
                </label>
                <select
                  id="registro-organizacion"
                  value={organizacionId}
                  onChange={manejarOrganizacion}
                  disabled={cargandoOrganizaciones}
                  className={claseCampo}
                >
                  <option value="">
                    {cargandoOrganizaciones
                      ? 'Cargando organizaciones...'
                      : 'Elegí tu organización...'}
                  </option>
                  {organizaciones.map((organizacion) => (
                    <option key={organizacion.id} value={organizacion.id}>
                      {organizacion.nombre}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {altaDeOng && (
              <>
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
                    maxLength={150}
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
              </>
            )}

            <button
              type="button"
              onClick={() => {
                setAltaDeOng((actual) => !actual)
                setError(null)
              }}
              className="text-left text-sm text-sky-400 hover:underline"
            >
              {altaDeOng
                ? '← Elegir una organización ya registrada'
                : '¿Tu ONG no está en la lista? Registrala'}
            </button>

            {errorOrganizaciones && (
              <p role="alert" className={claseAviso}>
                {errorOrganizaciones}
              </p>
            )}
          </div>
        )}

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
