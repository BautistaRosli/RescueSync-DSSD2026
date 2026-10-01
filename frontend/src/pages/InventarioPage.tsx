import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  actualizarRecurso,
  crearRecurso,
  eliminarRecurso,
  listarInventario,
  listarOfertasDeOrganizacion,
  listarLotes,
} from '../services'
import {
  claseBadge,
  claseBadgeAviso,
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
import type { LoteRead, RecursoInventario } from '../types'

interface Props {
  organizacionId: number
}

const VALORES_INICIALES = {
  tipo: '',
  cantidad: '',
  unidad: '',
  descripcion: '',
}

export function InventarioPage({ organizacionId }: Props) {
  const [recursos, setRecursos] = useState<RecursoInventario[]>([])
  const [comprometido, setComprometido] = useState<Record<string, number>>({})
  const [tipo, setTipo] = useState(VALORES_INICIALES.tipo)
  const [cantidad, setCantidad] = useState(VALORES_INICIALES.cantidad)
  const [unidad, setUnidad] = useState(VALORES_INICIALES.unidad)
  const [descripcion, setDescripcion] = useState(VALORES_INICIALES.descripcion)
  const [enEdicion, setEnEdicion] = useState<number | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [recargas, setRecargas] = useState(0)

  function recargar() {
    setRecargas((actuales) => actuales + 1)
  }

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const [inventario, ofertas] = await Promise.all([
          listarInventario(organizacionId),
          listarOfertasDeOrganizacion(organizacionId),
        ])

        const emergenciasDeOfertas = [
          ...new Set(ofertas.map((oferta) => oferta.emergencia_id)),
        ]
        const lotesPorEmergencia = await Promise.all(
          emergenciasDeOfertas.map((emergenciaId) => listarLotes(emergenciaId)),
        )
        const lotesPorId: Record<number, LoteRead> = {}
        for (const grupo of lotesPorEmergencia) {
          for (const lote of grupo) {
            lotesPorId[lote.id] = lote
          }
        }

        // Lo comprometido se agrupa por tipo de recurso, que es como se vinculan
        // el inventario local y los lotes de necesidad.
        const totales: Record<string, number> = {}
        for (const oferta of ofertas) {
          for (const item of oferta.items) {
            const lote = lotesPorId[item.lote_necesidad_id]
            if (lote === undefined) continue
            const clave = lote.tipo.trim().toLowerCase()
            totales[clave] = (totales[clave] ?? 0) + item.cantidad_ofrecida
          }
        }

        if (!vigente) return
        setRecursos(inventario)
        setComprometido(totales)
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

  function manejarTipo(evento: ChangeEvent<HTMLInputElement>) {
    setTipo(evento.target.value)
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

  function limpiarFormulario() {
    setEnEdicion(null)
    setTipo(VALORES_INICIALES.tipo)
    setCantidad(VALORES_INICIALES.cantidad)
    setUnidad(VALORES_INICIALES.unidad)
    setDescripcion(VALORES_INICIALES.descripcion)
    setError(null)
  }

  function editar(recurso: RecursoInventario) {
    setEnEdicion(recurso.id)
    setTipo(recurso.tipo)
    setCantidad(String(recurso.cantidad_total))
    setUnidad(recurso.unidad ?? '')
    setDescripcion(recurso.descripcion ?? '')
    setError(null)
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

    if (!tipo.trim()) {
      setError('Ingresá el tipo de recurso.')
      return
    }
    const cantidadNumero = Number(cantidad)
    if (!Number.isFinite(cantidadNumero) || cantidadNumero <= 0) {
      setError('Ingresá una cantidad mayor a 0.')
      return
    }

    const datos = {
      tipo: tipo.trim(),
      cantidad_total: Math.floor(cantidadNumero),
      unidad: unidad.trim() || null,
      descripcion: descripcion.trim() || null,
    }

    setGuardando(true)
    try {
      if (enEdicion !== null) {
        await actualizarRecurso(organizacionId, enEdicion, datos)
      } else {
        await crearRecurso(organizacionId, datos)
      }
      limpiarFormulario()
      recargar()
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(recursoId: number) {
    setError(null)
    try {
      await eliminarRecurso(organizacionId, recursoId)
      if (enEdicion === recursoId) {
        limpiarFormulario()
      }
      recargar()
    } catch (fallo) {
      setError(describirError(fallo))
    }
  }

  function comprometidoDe(recurso: RecursoInventario): number {
    return comprometido[recurso.tipo.trim().toLowerCase()] ?? 0
  }

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
          <input
            id="inventario-tipo"
            type="text"
            value={tipo}
            onChange={manejarTipo}
            placeholder="Paramédicos"
            maxLength={100}
            required
            className={claseCampo}
          />
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="sm:w-40">
            <label htmlFor="inventario-cantidad" className={claseEtiqueta}>
              Cantidad
            </label>
            <input
              id="inventario-cantidad"
              type="number"
              min={1}
              value={cantidad}
              onChange={manejarCantidad}
              placeholder="5"
              required
              className={claseCampo}
            />
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
            const usado = comprometidoDe(recurso)
            const disponible = recurso.cantidad_total - usado

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
                  <span className={claseBadge}>Comprometido: {usado}</span>
                  <span
                    className={disponible < 0 ? claseBadgeAviso : claseBadge}
                  >
                    Disponible: {disponible}
                  </span>
                </div>

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
                  <button
                    type="button"
                    onClick={() => void borrar(recurso.id)}
                    className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-red-500/50 hover:text-red-300"
                  >
                    Eliminar
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
