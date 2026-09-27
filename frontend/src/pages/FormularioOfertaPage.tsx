import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  actualizarOferta,
  crearOferta,
  crearOrganizacion,
  listarInventario,
  listarLotes,
  listarOrganizaciones,
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
import {
  convocatoriaAbierta,
  describirError,
  formatearFecha,
} from '../utils/formato'
import type {
  EmergenciaRead,
  LoteRead,
  OfertaCreateRequest,
  OfertaItemRequest,
  OfertaRead,
  OrganizacionRead,
  RecursoInventario,
} from '../types'

interface Props {
  organizacionId: number
  emergencia: EmergenciaRead
  ofertaExistente: OfertaRead | null
  onVolver: (huboCambios: boolean) => void
}

function textoDeCantidad(
  oferta: OfertaRead | null,
  loteId: number,
): string {
  const item = oferta?.items.find((i) => i.lote_necesidad_id === loteId)
  return item === undefined ? '' : String(item.cantidad_ofrecida)
}

function textoDeDescripcion(
  oferta: OfertaRead | null,
  loteId: number,
): string {
  const item = oferta?.items.find((i) => i.lote_necesidad_id === loteId)
  return item?.descripcion ?? ''
}

function disponibleEnInventario(
  inventario: RecursoInventario[],
  lote: LoteRead,
): RecursoInventario | undefined {
  return inventario.find(
    (recurso) => recurso.tipo.trim().toLowerCase() === lote.tipo.trim().toLowerCase(),
  )
}

function cantidadDeTexto(texto: string): number {
  const numero = Number(texto)
  return Number.isFinite(numero) && numero > 0 ? Math.floor(numero) : 0
}

export function FormularioOfertaPage({
  organizacionId,
  emergencia,
  ofertaExistente,
  onVolver,
}: Props) {
  const [lotes, setLotes] = useState<LoteRead[]>([])
  const [organizaciones, setOrganizaciones] = useState<OrganizacionRead[]>([])
  const [inventario, setInventario] = useState<RecursoInventario[]>([])
  const [cantidades, setCantidades] = useState<Record<number, string>>({})
  const [descripciones, setDescripciones] = useState<Record<number, string>>({})
  const [observaciones, setObservaciones] = useState(
    ofertaExistente?.observaciones ?? '',
  )
  const [esConjunta, setEsConjunta] = useState(
    ofertaExistente?.es_conjunta ?? false,
  )
  const [sociasIds, setSociasIds] = useState<number[]>(
    ofertaExistente?.organizaciones
      .map((organizacion) => organizacion.id)
      .filter((id) => id !== organizacionId) ?? [],
  )
  const [nombreOngNueva, setNombreOngNueva] = useState('')
  const [creandoOng, setCreandoOng] = useState(false)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [guardada, setGuardada] = useState<OfertaRead | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const [lotesCargados, organizacionesCargadas, inventarioCargado] =
          await Promise.all([
            listarLotes(emergencia.id),
            listarOrganizaciones(),
            listarInventario(organizacionId),
          ])
        if (!vigente) return
        setLotes(lotesCargados)
        setOrganizaciones(organizacionesCargadas)
        setInventario(inventarioCargado)
        setCantidades(
          Object.fromEntries(
            lotesCargados.map((lote) => [
              lote.id,
              textoDeCantidad(ofertaExistente, lote.id),
            ]),
          ),
        )
        setDescripciones(
          Object.fromEntries(
            lotesCargados.map((lote) => [
              lote.id,
              textoDeDescripcion(ofertaExistente, lote.id),
            ]),
          ),
        )
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
  }, [emergencia.id, organizacionId, ofertaExistente])

  function manejarCantidad(loteId: number) {
    return (evento: ChangeEvent<HTMLInputElement>) => {
      const valor = evento.target.value
      setCantidades((actuales) => ({ ...actuales, [loteId]: valor }))
    }
  }

  function manejarDescripcion(loteId: number) {
    return (evento: ChangeEvent<HTMLInputElement>) => {
      const valor = evento.target.value
      setDescripciones((actuales) => ({ ...actuales, [loteId]: valor }))
    }
  }

  function manejarObservaciones(evento: ChangeEvent<HTMLTextAreaElement>) {
    setObservaciones(evento.target.value)
  }

  function manejarEsConjunta(evento: ChangeEvent<HTMLInputElement>) {
    const marcada = evento.target.checked
    setEsConjunta(marcada)
    if (!marcada) {
      setSociasIds([])
    }
  }

  function agregarSocia(evento: ChangeEvent<HTMLSelectElement>) {
    const id = Number(evento.target.value)
    if (id > 0) {
      setSociasIds((actuales) =>
        actuales.includes(id) ? actuales : [...actuales, id],
      )
    }
    evento.target.value = ''
  }

  function quitarSocia(id: number) {
    setSociasIds((actuales) => actuales.filter((socia) => socia !== id))
  }

  async function registrarOngNueva() {
    const nombre = nombreOngNueva.trim()
    if (nombre.length < 2) {
      setError('Ingresá el nombre de la ONG socia (mínimo 2 caracteres).')
      return
    }
    setError(null)
    setCreandoOng(true)
    try {
      const creada = await crearOrganizacion({ nombre, tipo: 'ong' })
      setOrganizaciones((actuales) => [...actuales, creada])
      setSociasIds((actuales) => [...actuales, creada.id])
      setNombreOngNueva('')
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setCreandoOng(false)
    }
  }

  function construirItems(): OfertaItemRequest[] {
    return lotes
      .map((lote) => ({
        lote_necesidad_id: lote.id,
        cantidad_ofrecida: cantidadDeTexto(cantidades[lote.id] ?? ''),
        descripcion: (descripciones[lote.id] ?? '').trim() || null,
      }))
      .filter((item) => item.cantidad_ofrecida > 0)
  }

  async function manejarEnvio(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setError(null)

    if (!convocatoriaAbierta(emergencia)) {
      setError(
        'La ventana de convocatoria está cerrada: ya no se pueden cargar ni modificar ofertas.',
      )
      return
    }

    const items = construirItems()
    if (items.length === 0) {
      setError('Ingresá una cantidad mayor a 0 en al menos un lote.')
      return
    }
    if (esConjunta && sociasIds.length === 0) {
      setError('Agregá al menos una ONG socia o desmarcá la oferta conjunta.')
      return
    }

    setEnviando(true)
    try {
      if (ofertaExistente !== null) {
        setGuardada(
          await actualizarOferta(ofertaExistente.id, {
            observaciones: observaciones.trim() || null,
            items,
            organizaciones_ids: sociasIds,
            es_conjunta: esConjunta,
          }),
        )
      } else {
        const datos: OfertaCreateRequest = {
          emergencia_id: emergencia.id,
          organizacion_id: organizacionId,
          observaciones: observaciones.trim() || null,
          items,
          organizaciones_ids: sociasIds,
          es_conjunta: esConjunta,
        }
        setGuardada(await crearOferta(datos))
      }
    } catch (fallo) {
      setError(describirError(fallo))
    } finally {
      setEnviando(false)
    }
  }

  const sociasDisponibles = organizaciones.filter(
    (organizacion) =>
      organizacion.id !== organizacionId && !sociasIds.includes(organizacion.id),
  )

  function nombreDeOrganizacion(id: number): string {
    return organizaciones.find((o) => o.id === id)?.nombre ?? `ONG #${id}`
  }

  if (guardada !== null) {
    const totalOfrecido = guardada.items.reduce(
      (suma, item) => suma + item.cantidad_ofrecida,
      0,
    )

    return (
      <section className="flex flex-col gap-6">
        <div className="rounded-xl bg-slate-800 border border-emerald-500/40 p-6 shadow-2xl">
          <h2 className="text-xl font-bold text-emerald-400 mb-1">
            {ofertaExistente !== null ? 'Oferta actualizada' : 'Oferta registrada'}
          </h2>
          <p className="text-sm text-slate-400 mb-5">
            Tu postulación quedó cargada para la emergencia de{' '}
            {emergencia.zona_afectada}. Podés seguir modificándola mientras la
            convocatoria siga abierta.
          </p>

          <dl className={claseSubPanel}>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Id de la oferta</dt>
              <dd className="font-mono text-cyan-400">{guardada.id}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Lotes cubiertos</dt>
              <dd className="font-mono text-cyan-400">{guardada.items.length}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Total ofrecido</dt>
              <dd className="font-mono text-cyan-400">{totalOfrecido}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Tipo de oferta</dt>
              <dd className="font-mono text-cyan-400">
                {guardada.es_conjunta ? 'Conjunta (consorcio)' : 'Individual'}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Organizaciones</dt>
              <dd className="font-mono text-cyan-400 break-all">
                {guardada.organizaciones
                  .map((organizacion) => organizacion.nombre)
                  .join(', ')}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-1">
              <dt className="text-slate-400">Registrada el</dt>
              <dd className="font-mono text-cyan-400">
                {formatearFecha(guardada.fecha_hora_oferta, 'Sin fecha')}
              </dd>
            </div>
          </dl>

          <button
            type="button"
            onClick={() => onVolver(true)}
            className={`mt-4 w-full ${claseBotonPrimario}`}
          >
            Volver a convocatorias
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-6">
      <div className={claseCard}>
        <h2 className={claseTitulo}>
          {ofertaExistente !== null ? 'Editar mi oferta' : 'Postular recursos'}
        </h2>
        <p className={claseSubtitulo}>
          Emergencia en {emergencia.zona_afectada}. Indicá cuánto puede aportar tu
          organización en cada lote. Podés cubrir solo una parte: dejá en blanco o
          en 0 los lotes que no vas a cubrir.
        </p>
      </div>

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando lotes de la convocatoria...
        </p>
      )}

      {!cargando && lotes.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Esta emergencia todavía no tiene lotes de necesidad publicados.
        </p>
      )}

      {!cargando && lotes.length > 0 && (
        <form
          onSubmit={manejarEnvio}
          className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl flex flex-col gap-4"
          noValidate
        >
          <h3 className="text-lg font-bold text-cyan-400">Recursos a ofertar</h3>

          {lotes.map((lote) => {
            const recurso = disponibleEnInventario(inventario, lote)
            const ofrecido = cantidadDeTexto(cantidades[lote.id] ?? '')
            const excedeInventario =
              recurso !== undefined && ofrecido > recurso.cantidad_total

            return (
              <div key={lote.id} className={claseSubPanel}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-base font-semibold text-white">
                    {lote.tipo}
                  </span>
                  <span className={claseBadge}>
                    Requerido: {lote.cantidad}
                    {lote.unidad ? ` ${lote.unidad}` : ''}
                  </span>
                </div>

                {lote.descripcion && (
                  <p className="mt-1 text-xs text-slate-400">{lote.descripcion}</p>
                )}

                <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                  <div className="sm:w-40">
                    <label
                      htmlFor={`oferta-cantidad-${lote.id}`}
                      className={claseEtiqueta}
                    >
                      Cantidad
                    </label>
                    <input
                      id={`oferta-cantidad-${lote.id}`}
                      type="number"
                      min={0}
                      max={999999}
                      value={cantidades[lote.id] ?? ''}
                      onChange={manejarCantidad(lote.id)}
                      placeholder="0"
                      className={claseCampo}
                    />
                  </div>

                  <div className="flex-1">
                    <label
                      htmlFor={`oferta-detalle-${lote.id}`}
                      className={claseEtiqueta}
                    >
                      Detalle del recurso
                    </label>
                    <input
                      id={`oferta-detalle-${lote.id}`}
                      type="text"
                      value={descripciones[lote.id] ?? ''}
                      onChange={manejarDescripcion(lote.id)}
                      placeholder="Personal con certificación vigente, disponible 72 h"
                      className={claseCampo}
                    />
                  </div>
                </div>

                {recurso !== undefined && (
                  <p className="mt-2 text-xs text-slate-400">
                    Disponible en tu inventario: {recurso.cantidad_total}
                    {recurso.unidad ? ` ${recurso.unidad}` : ''}
                  </p>
                )}

                {excedeInventario && (
                  <p className="mt-2 inline-block">
                    <span className={claseBadgeAviso}>
                      Estás ofreciendo más de lo que figura en tu inventario
                    </span>
                  </p>
                )}
              </div>
            )
          })}

          <div>
            <label htmlFor="oferta-observaciones" className={claseEtiqueta}>
              Observaciones
            </label>
            <textarea
              id="oferta-observaciones"
              value={observaciones}
              onChange={manejarObservaciones}
              placeholder="Condiciones de traslado, tiempos de llegada, contacto responsable."
              rows={3}
              className={claseCampo}
            />
          </div>

          <div className={claseSubPanel}>
            <label className="flex items-start gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={esConjunta}
                onChange={manejarEsConjunta}
                className="mt-1"
              />
              <span>
                Esta es una oferta conjunta (consorcio con otras ONGs)
                <span className="mt-1 block text-xs text-slate-400">
                  Las organizaciones que agregues quedan registradas como
                  responsables junto a la tuya y ven la oferta en su propio panel.
                </span>
              </span>
            </label>

            {esConjunta && (
              <div className="mt-4 flex flex-col gap-3">
                {sociasIds.length > 0 && (
                  <ul className="flex flex-wrap gap-2">
                    {sociasIds.map((id) => (
                      <li key={id}>
                        <button
                          type="button"
                          onClick={() => quitarSocia(id)}
                          className="rounded-full border border-cyan-500/50 bg-cyan-500/10 px-3 py-0.5 text-xs text-cyan-300 transition hover:border-red-500/50 hover:text-red-300"
                        >
                          {nombreDeOrganizacion(id)} ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <div>
                  <label htmlFor="oferta-socia" className={claseEtiqueta}>
                    Agregar ONG a la oferta
                  </label>
                  <select
                    id="oferta-socia"
                    defaultValue=""
                    onChange={agregarSocia}
                    disabled={sociasDisponibles.length === 0}
                    className={claseCampo}
                  >
                    <option value="">
                      {sociasDisponibles.length === 0
                        ? 'No hay otras organizaciones registradas'
                        : 'Elegí una organización...'}
                    </option>
                    {sociasDisponibles.map((organizacion) => (
                      <option key={organizacion.id} value={organizacion.id}>
                        {organizacion.nombre}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="oferta-ong-nueva" className={claseEtiqueta}>
                    ¿La ONG socia no está en la lista? Registrala
                  </label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                      id="oferta-ong-nueva"
                      type="text"
                      value={nombreOngNueva}
                      onChange={(evento) => setNombreOngNueva(evento.target.value)}
                      placeholder="Nombre de la organización"
                      maxLength={150}
                      className={claseCampo}
                    />
                    <button
                      type="button"
                      onClick={registrarOngNueva}
                      disabled={creandoOng}
                      className={claseBotonSecundario}
                    >
                      {creandoOng ? 'Agregando...' : 'Agregar'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {error && (
            <p role="alert" className={claseError}>
              {error}
            </p>
          )}

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="submit"
              disabled={enviando}
              className={`flex-1 ${claseBotonPrimario}`}
            >
              {enviando
                ? 'Guardando...'
                : ofertaExistente !== null
                  ? 'Guardar cambios'
                  : 'Postular recursos'}
            </button>
            <button
              type="button"
              onClick={() => onVolver(false)}
              className={claseBotonSecundario}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {!cargando && lotes.length === 0 && error === null && (
        <button
          type="button"
          onClick={() => onVolver(false)}
          className={claseBotonSecundario}
        >
          Volver a convocatorias
        </button>
      )}
    </section>
  )
}
