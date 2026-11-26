import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  actualizarRecurso,
  crearRecurso,
  eliminarRecurso,
  listarCatalogoRecursosCloud,
  listarInventario,
} from '../services'
import {
  claseBadge,
  claseBadgeAviso,
  claseBadgeExito,
  claseBotonPrimario,
  claseBotonSecundario,
  claseCampo,
  claseCard,
  claseError,
  claseEtiqueta,
  claseSubPanel,
  claseSubtitulo,
  claseTitulo,
} from '../ui/clases'
import { describirError } from '../utils/formato'
import type { RecursoCloud, RecursoInventario } from '../types'

interface Props {
  organizacionId: number
}

const VALORES_INICIALES = {
  tipoRecursoId: '',
  cantidad: '',
  unidad: '',
  descripcion: '',
}

function mostrarCantidad(valor: number | null): string {
  return valor === null ? '—' : String(valor)
}

export function InventarioPage({ organizacionId }: Props) {
  const formularioRef = useRef<HTMLFormElement>(null)
  const [recursos, setRecursos] = useState<RecursoInventario[]>([])
  const [catalogo, setCatalogo] = useState<RecursoCloud[]>([])
  const [tipoRecursoId, setTipoRecursoId] = useState(VALORES_INICIALES.tipoRecursoId)
  const [cantidad, setCantidad] = useState(VALORES_INICIALES.cantidad)
  const [unidad, setUnidad] = useState(VALORES_INICIALES.unidad)
  const [descripcion, setDescripcion] = useState(VALORES_INICIALES.descripcion)
  const [enEdicion, setEnEdicion] = useState<number | null>(null)
  const [vinculos, setVinculos] = useState<Record<number, string>>({})
  const [vinculandoId, setVinculandoId] = useState<number | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [recargas, setRecargas] = useState(0)
  const [confirmacionesPendientes, setConfirmacionesPendientes] = useState<Record<number, boolean>>({})
  const [eliminandoId, setEliminandoId] = useState<number | null>(null)

  function recargar() {
    setRecargas((actuales) => actuales + 1)
  }

  useEffect(() => {
    let vigente = true

    async function cargarCatalogo() {
      try {
        const recursosNacionales = await listarCatalogoRecursosCloud()
        if (vigente) setCatalogo(recursosNacionales)
      } catch (fallo) {
        if (vigente) setError(describirError(fallo))
      }
    }

    void cargarCatalogo()

    return () => {
      vigente = false
    }
  }, [])

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const inventario = await listarInventario(organizacionId)
        if (vigente) setRecursos(inventario)
      } catch (fallo) {
        if (vigente) setError(describirError(fallo))
      } finally {
        if (vigente) setCargando(false)
      }
    }

    void cargar()

    return () => {
      vigente = false
    }
  }, [organizacionId, recargas])

  function manejarTipoRecurso(evento: ChangeEvent<HTMLSelectElement>) {
    setTipoRecursoId(evento.target.value)
  }

  function manejarCantidad(evento: ChangeEvent<HTMLInputElement>) {
    setCantidad(evento.target.value)
  }

  function manejarUnidad(evento: ChangeEvent<HTMLInputElement>) {
    setUnidad(evento.target.value)
  }

  function manejarDescripcion(evento: ChangeEvent<HTMLInputElement>) {
    setDescripcion(evento.target.value)
  }

  function manejarVinculo(recursoId: number) {
    return (evento: ChangeEvent<HTMLSelectElement>) => {
      const valor = evento.target.value
      setVinculos((actuales) => ({ ...actuales, [recursoId]: valor }))
    }
  }

  function limpiarFormulario() {
    setEnEdicion(null)
    setTipoRecursoId(VALORES_INICIALES.tipoRecursoId)
    setCantidad(VALORES_INICIALES.cantidad)
    setUnidad(VALORES_INICIALES.unidad)
    setDescripcion(VALORES_INICIALES.descripcion)
    setError(null)
  }

  function editar(recurso: RecursoInventario) {
    setEnEdicion(recurso.id)
    setTipoRecursoId(
      recurso.tipo_recurso_id === null ? '' : String(recurso.tipo_recurso_id),
    )
    setCantidad(String(recurso.cantidad_total))
    setUnidad(recurso.unidad ?? '')
    setDescripcion(recurso.descripcion ?? '')
    setError(null)
    formularioRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

    const idSeleccionado = Number(tipoRecursoId)
    const haySeleccion = tipoRecursoId !== '' && idSeleccionado > 0
    if (enEdicion === null && !haySeleccion) {
      setError('Elegí el recurso del catálogo del Sistema Nacional.')
      return
    }
    const cantidadNumero = Number(cantidad)
    if (!Number.isFinite(cantidadNumero) || cantidadNumero <= 0) {
      setError('Ingresá una cantidad mayor a 0.')
      return
    }

    const cantidadTotal = Math.floor(cantidadNumero)
    const cantidadMinima = minimoDeCantidad()
    if (cantidadTotal < cantidadMinima) {
      setError(`La cantidad total no puede ser menor que la cantidad comprometida (${cantidadMinima}).`)
      return
    }

    const unidadFinal = unidad.trim() || null
    const descripcionFinal = descripcion.trim() || null

    setGuardando(true)
    try {
      if (enEdicion !== null) {
        const enEdicionSinVinculo = recursoEnEdicion()?.tipo_recurso_id === null
        await actualizarRecurso(organizacionId, enEdicion, {
          cantidad_total: cantidadTotal,
          unidad: unidadFinal,
          descripcion: descripcionFinal,
          ...(enEdicionSinVinculo && haySeleccion
            ? { tipo_recurso_id: idSeleccionado }
            : {}),
        })
      } else {
        await crearRecurso(organizacionId, {
          tipo_recurso_id: idSeleccionado,
          cantidad_total: cantidadTotal,
          unidad: unidadFinal,
          descripcion: descripcionFinal,
        })
      }
      limpiarFormulario()
      recargar()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setGuardando(false)
    }
  }

  async function vincular(recurso: RecursoInventario) {
    const idSeleccionado = Number(vinculos[recurso.id] ?? '')
    if (!(idSeleccionado > 0)) {
      setError('Elegí el recurso del catálogo para vincular.')
      return
    }

    setError(null)
    setVinculandoId(recurso.id)
    try {
      await actualizarRecurso(organizacionId, recurso.id, {
        tipo_recurso_id: idSeleccionado,
        cantidad_total: recurso.cantidad_total,
        unidad: recurso.unidad,
        descripcion: recurso.descripcion,
      })
      setVinculos((actuales) => {
        const siguientes = { ...actuales }
        delete siguientes[recurso.id]
        return siguientes
      })
      recargar()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setVinculandoId(null)
    }
  }

  function solicitarConfirmacionBorrado(recursoId: number) {
    setConfirmacionesPendientes({ [recursoId]: true })
  }

  function cancelarConfirmacionBorrado(recursoId: number) {
    setConfirmacionesPendientes((previas) => ({ ...previas, [recursoId]: false }))
  }

  async function borrar(recursoId: number) {
    setError(null)
    setEliminandoId(recursoId)
    try {
      await eliminarRecurso(organizacionId, recursoId)
      if (enEdicion === recursoId) {
        limpiarFormulario()
      }
      recargar()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEliminandoId(null)
      setConfirmacionesPendientes({})
    }
  }

  function recursoEnEdicion(): RecursoInventario | undefined {
    if (enEdicion === null) return undefined
    return recursos.find((item) => item.id === enEdicion)
  }

  function comprometidoEnEdicion(): number {
    return recursoEnEdicion()?.comprometido ?? 0
  }

  function minimoDeCantidad(): number {
    return Math.max(1, comprometidoEnEdicion())
  }

  const edicionVinculada =
    enEdicion !== null && recursoEnEdicion()?.tipo_recurso_id != null

  return (
    <section className="flex flex-col gap-4">
      <div className={claseCard}>
        <h2 className={claseTitulo}>Inventario de recursos</h2>
        <p className={claseSubtitulo}>
          Cargá el personal y los materiales que tu organización puede movilizar.
          El formulario de postulación usa estos datos para mostrarte cuánto tenés
          disponible en cada lote.
        </p>
      </div>

      <form
        ref={formularioRef}
        onSubmit={manejarEnvio}
        className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl flex flex-col gap-4"
        noValidate
      >
        <h3 className="text-lg font-bold text-cyan-400">
          {enEdicion !== null ? 'Editar recurso' : 'Agregar recurso'}
        </h3>

        <div>
          <label htmlFor="inventario-tipo" className={claseEtiqueta}>
            Tipo de recurso
          </label>
          {edicionVinculada ? (
            <input
              id="inventario-tipo"
              type="text"
              value={recursoEnEdicion()?.tipo ?? ''}
              disabled
              className={claseCampo}
            />
          ) : (
            <select
              id="inventario-tipo"
              value={tipoRecursoId}
              onChange={manejarTipoRecurso}
              required={enEdicion === null}
              className={claseCampo}
            >
              <option value="">
                {catalogo.length === 0
                  ? 'Sin recursos en el catálogo nacional'
                  : 'Elegí un recurso del catálogo nacional'}
              </option>
              {catalogo.map((recursoNacional) => (
                <option key={recursoNacional.id} value={recursoNacional.id}>
                  {recursoNacional.nombre}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="sm:w-40">
            <label htmlFor="inventario-cantidad" className={claseEtiqueta}>
              Cantidad
            </label>
            <input
              id="inventario-cantidad"
              type="number"
              min={minimoDeCantidad()}
              value={cantidad}
              onChange={manejarCantidad}
              placeholder="5"
              required
              className={claseCampo}
            />
            {enEdicion !== null && comprometidoEnEdicion() > 0 && (
              <p className="mt-1 text-xs text-slate-400">
                Mínimo comprometido: {minimoDeCantidad()}
              </p>
            )}
          </div>

          <div className="flex-1">
            <label htmlFor="inventario-unidad" className={claseEtiqueta}>
              Unidad
            </label>
            <input
              id="inventario-unidad"
              type="text"
              value={unidad}
              onChange={manejarUnidad}
              placeholder="personas, raciones, litros"
              maxLength={50}
              className={claseCampo}
            />
          </div>
        </div>

        <div>
          <label htmlFor="inventario-descripcion" className={claseEtiqueta}>
            Descripción
          </label>
          <input
            id="inventario-descripcion"
            type="text"
            value={descripcion}
            onChange={manejarDescripcion}
            placeholder="Certificación vigente, disponibilidad inmediata"
            className={claseCampo}
          />
        </div>

        {error && (
          <p role="alert" className={claseError}>
            {error}
          </p>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="submit"
            disabled={guardando}
            className={`flex-1 ${claseBotonPrimario}`}
          >
            {guardando
              ? 'Guardando...'
              : enEdicion !== null
                ? 'Guardar cambios'
                : 'Agregar recurso'}
          </button>
          {enEdicion !== null && (
            <button
              type="button"
              onClick={limpiarFormulario}
              className={claseBotonSecundario}
            >
              Cancelar
            </button>
          )}
        </div>
      </form>

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando inventario...
        </p>
      )}

      {!cargando && recursos.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Todavía no cargaste recursos en tu inventario.
        </p>
      )}

      {!cargando && recursos.length > 0 && (
        <ul className="flex flex-col gap-3">
          {recursos.map((recurso) => {
            return (
              <li
                key={recurso.id}
                className="rounded-xl bg-slate-800 border border-slate-700 p-4 shadow-2xl"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-base font-semibold text-white">
                    {recurso.tipo}
                  </span>
                  <span className="font-mono text-xs text-cyan-400">
                    {recurso.cantidad_total}
                    {recurso.unidad ? ` ${recurso.unidad}` : ''}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap gap-2">
                  <span className={claseBadge}>Total: {recurso.cantidad_total}</span>
                  <span className={claseBadge}>
                    Comprometido: {mostrarCantidad(recurso.comprometido)}
                  </span>
                  <span className={claseBadge}>
                    Disponible: {mostrarCantidad(recurso.disponible)}
                  </span>
                  {recurso.tipo_recurso_id === null ? (
                    <span className={claseBadgeAviso}>
                      Sin vincular al Sistema Nacional
                    </span>
                  ) : recurso.sincronizado ? (
                    <span className={claseBadgeExito}>
                      Sincronizado con el Sistema Nacional
                    </span>
                  ) : (
                    <span className={claseBadgeAviso}>
                      No se pudo consultar el Sistema Nacional
                    </span>
                  )}
                </div>

                {recurso.tipo_recurso_id === null && (
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                    <label htmlFor={`inventario-vinculo-${recurso.id}`} className="sr-only">
                      Recurso del catálogo nacional
                    </label>
                    <select
                      id={`inventario-vinculo-${recurso.id}`}
                      value={vinculos[recurso.id] ?? ''}
                      onChange={manejarVinculo(recurso.id)}
                      className={`flex-1 ${claseCampo}`}
                    >
                      <option value="">Elegí el recurso del catálogo nacional</option>
                      {catalogo.map((recursoNacional) => (
                        <option key={recursoNacional.id} value={recursoNacional.id}>
                          {recursoNacional.nombre}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => void vincular(recurso)}
                      disabled={vinculandoId === recurso.id}
                      className={claseBotonSecundario}
                    >
                      {vinculandoId === recurso.id ? 'Vinculando...' : 'Vincular'}
                    </button>
                  </div>
                )}

                {recurso.descripcion && (
                  <p className="mt-2 text-xs text-slate-400">
                    {recurso.descripcion}
                  </p>
                )}

                <div className={`mt-3 ${claseSubPanel} flex flex-wrap gap-2`}>
                  <button
                    type="button"
                    onClick={() => editar(recurso)}
                    className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
                  >
                    Editar
                  </button>
                  {confirmacionesPendientes[recurso.id] === true ? (
                    <div
                      role="group"
                      aria-label={`Confirmar eliminación del recurso ${recurso.tipo}`}
                      className="flex flex-col gap-2 rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-3"
                    >
                      <p className="text-sm text-yellow-200">
                        ¿Eliminar {recurso.tipo}? La acción no se puede deshacer.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void borrar(recurso.id)}
                          disabled={eliminandoId !== null}
                          className={`${claseBotonSecundario} text-sm`}
                        >
                          {eliminandoId === recurso.id ? 'Eliminando...' : 'Confirmar eliminación'}
                        </button>
                        <button
                          type="button"
                          onClick={() => cancelarConfirmacionBorrado(recurso.id)}
                          disabled={eliminandoId !== null}
                          className={`${claseBotonSecundario} text-sm`}
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => solicitarConfirmacionBorrado(recurso.id)}
                      disabled={eliminandoId !== null}
                      className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-red-500/50 hover:text-red-300"
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
