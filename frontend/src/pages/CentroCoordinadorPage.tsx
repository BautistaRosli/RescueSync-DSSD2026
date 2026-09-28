import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  actualizarLote,
  crearLote,
  eliminarLote,
  listarBandejaEmergencias,
  publicarEmergencia,
} from '../services'
import type {
  BandaEmergencias,
  EstadoEmergencia,
  EmergenciaRead,
  LoteNecesidad,
  NivelGravedad,
} from '../types'

type PestaniaBandeja = 'sin_publicar' | 'publicadas'

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

const PESTANIAS_BANDEJA: {
  valor: PestaniaBandeja
  etiqueta: string
  titulo: string
}[] = [
  {
    valor: 'sin_publicar',
    etiqueta: 'Sin publicar',
    titulo: 'Emergencias sin publicar',
  },
  { valor: 'publicadas', etiqueta: 'Publicadas', titulo: 'Emergencias publicadas' },
]

const DESCRIPCIONES_BANDEJA: Record<PestaniaBandeja, string> = {
  sin_publicar:
    'Emergencias a la espera de lotes. Tocá una fila para desplegar su detalle, cargarle sus lotes o publicarla.',
  publicadas:
    'Emergencias a la espera de ofertas de ayuda. Tocá una fila para desplegar su detalle.',
}

const POR_PAGINA = 10

const clasePestania = (activa: boolean): string =>
  activa
    ? 'rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-900'
    : 'rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400'

const claseError =
  'rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300'

const claseCampo =
  'w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white placeholder-slate-500 focus:border-cyan-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60'

const claseEtiqueta = 'block text-sm text-slate-300 mb-1'

interface BorradorLote {
  tipo: string
  cantidad: string
  unidad: string
  descripcion: string
}

const BORRADOR_VACIO: BorradorLote = {
  tipo: '',
  cantidad: '',
  unidad: '',
  descripcion: '',
}

function etiquetaDeGravedad(nivel: NivelGravedad): string {
  return NIVELES_GRAVEDAD.find((opcion) => opcion.valor === nivel)?.etiqueta ?? nivel
}

const CLASES_GRAVEDAD: Record<NivelGravedad, string> = {
  baja: 'rounded-full border border-emerald-500/50 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300',
  media: 'rounded-full border border-yellow-500/50 bg-yellow-500/10 px-2 py-0.5 text-xs text-yellow-300',
  alta: 'rounded-full border border-orange-500/50 bg-orange-500/10 px-2 py-0.5 text-xs text-orange-300',
  critica: 'rounded-full border border-red-500/50 bg-red-500/10 px-2 py-0.5 text-xs text-red-300',
}

function clasesDeGravedad(nivel: NivelGravedad): string {
  return CLASES_GRAVEDAD[nivel]
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
    if (error.status === 422) {
      return `Revisá los datos enviados. ${error.detail}`
    }
    return error.detail
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.'
}

function idPanel(emergenciaId: number): string {
  return `detalle-bandeja-${emergenciaId}`
}

function sinClave<T>(registro: Record<number, T>, clave: number): Record<number, T> {
  const siguiente = { ...registro }
  delete siguiente[clave]
  return siguiente
}

function DetalleEmergencia({ emergencia }: { emergencia: EmergenciaRead }) {
  return (
    <div
      id={idPanel(emergencia.id)}
      className="rounded-lg bg-slate-900 border border-slate-700 p-4 text-sm"
    >
      <dl className="flex flex-col">
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
      </dl>

      <div className="mt-4 border-t border-slate-700 pt-3">
        <p className="text-xs font-semibold text-slate-400">Descripción inicial</p>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
          {emergencia.descripcion_inicial}
        </p>
      </div>
    </div>
  )
}

function ListaLotes({
  lotes,
  editable,
  loteEnEdicion,
  borradorEdicion,
  errorEdicion,
  guardandoEdicion,
  eliminandoLote,
  alAbrirEdicion,
  alCancelarEdicion,
  alCambiarCampoEdicion,
  alEnviarEdicion,
  alEliminar,
}: {
  lotes: LoteNecesidad[]
  editable: boolean
  loteEnEdicion: number | null
  borradorEdicion: BorradorLote
  errorEdicion: string | undefined
  guardandoEdicion: boolean
  eliminandoLote: number | null
  alAbrirEdicion: (lote: LoteNecesidad) => void
  alCancelarEdicion: () => void
  alCambiarCampoEdicion: (campo: keyof BorradorLote, valor: string) => void
  alEnviarEdicion: (
    evento: FormEvent<HTMLFormElement>,
    lote: LoteNecesidad,
  ) => void
  alEliminar: (lote: LoteNecesidad) => void
}) {
  if (lotes.length === 0) {
    return (
      <p className="mt-4 border-t border-slate-700 pt-3 text-sm text-slate-400">
        Todavía no tiene lotes de necesidad cargados.
      </p>
    )
  }

  return (
    <div className="mt-4 border-t border-slate-700 pt-3">
      <p className="text-xs font-semibold text-slate-400">
        Lotes de necesidad ({lotes.length})
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {lotes.map((lote) =>
          editable && loteEnEdicion === lote.id ? (
            <li
              key={lote.id}
              className="rounded-lg bg-slate-900 border border-cyan-500/50 p-3 text-sm"
            >
              <form
                onSubmit={(evento) => alEnviarEdicion(evento, lote)}
                className="flex flex-col gap-3"
                noValidate
              >
                <p className="text-xs font-semibold text-cyan-400">
                  Editando lote #{lote.id}
                </p>

                <div>
                  <label
                    htmlFor={`lote-edicion-${lote.id}-tipo`}
                    className={claseEtiqueta}
                  >
                    Tipo
                  </label>
                  <input
                    id={`lote-edicion-${lote.id}-tipo`}
                    type="text"
                    value={borradorEdicion.tipo}
                    onChange={(evento) =>
                      alCambiarCampoEdicion('tipo', evento.target.value)
                    }
                    placeholder="Colchones"
                    maxLength={120}
                    required
                    className={claseCampo}
                  />
                </div>

                <div className="flex flex-wrap gap-3">
                  <div className="flex-1 min-w-32">
                    <label
                      htmlFor={`lote-edicion-${lote.id}-cantidad`}
                      className={claseEtiqueta}
                    >
                      Cantidad
                    </label>
                    <input
                      id={`lote-edicion-${lote.id}-cantidad`}
                      type="number"
                      min={1}
                      step={1}
                      value={borradorEdicion.cantidad}
                      onChange={(evento) =>
                        alCambiarCampoEdicion('cantidad', evento.target.value)
                      }
                      placeholder="50"
                      required
                      className={claseCampo}
                    />
                  </div>

                  <div className="flex-1 min-w-32">
                    <label
                      htmlFor={`lote-edicion-${lote.id}-unidad`}
                      className={claseEtiqueta}
                    >
                      Unidad (opcional)
                    </label>
                    <input
                      id={`lote-edicion-${lote.id}-unidad`}
                      type="text"
                      value={borradorEdicion.unidad}
                      onChange={(evento) =>
                        alCambiarCampoEdicion('unidad', evento.target.value)
                      }
                      placeholder="unidades"
                      maxLength={50}
                      className={claseCampo}
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor={`lote-edicion-${lote.id}-descripcion`}
                    className={claseEtiqueta}
                  >
                    Descripción (opcional)
                  </label>
                  <textarea
                    id={`lote-edicion-${lote.id}-descripcion`}
                    value={borradorEdicion.descripcion}
                    onChange={(evento) =>
                      alCambiarCampoEdicion('descripcion', evento.target.value)
                    }
                    placeholder="Detalle del lote, dónde se entrega, prioridad."
                    rows={2}
                    className={claseCampo}
                  />
                </div>

                {errorEdicion !== undefined && (
                  <p role="alert" className={claseError}>
                    {errorEdicion}
                  </p>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="submit"
                    disabled={guardandoEdicion}
                    className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {guardandoEdicion ? 'Guardando...' : 'Guardar'}
                  </button>
                  <button
                    type="button"
                    onClick={alCancelarEdicion}
                    disabled={guardandoEdicion}
                    className="rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            </li>
          ) : (
            <li
              key={lote.id}
              className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-sm"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold text-white">{lote.tipo}</span>
                <span className="font-mono text-cyan-400">
                  {lote.cantidad} {lote.unidad ?? 'unidades'}
                </span>
              </div>
              {lote.descripcion !== null && (
                <p className="mt-1 whitespace-pre-wrap text-xs text-slate-400">
                  {lote.descripcion}
                </p>
              )}
              {editable && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => alAbrirEdicion(lote)}
                    disabled={eliminandoLote !== null}
                    className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    onClick={() => alEliminar(lote)}
                    disabled={eliminandoLote !== null}
                    className="rounded-lg border border-red-500/50 px-3 py-1 text-xs font-semibold text-red-300 transition hover:border-red-400 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {eliminandoLote === lote.id ? 'Eliminando...' : 'Eliminar'}
                  </button>
                </div>
              )}
            </li>
          ),
        )}
      </ul>
    </div>
  )
}

export function CentroCoordinadorPage() {
  const [pestania, setPestania] = useState<PestaniaBandeja>('sin_publicar')
  const [pagina, setPagina] = useState(1)
  const [bandeja, setBandeja] = useState<BandaEmergencias | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recargo, setRecargo] = useState(0)
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())
  const [borradores, setBorradores] = useState<Record<number, BorradorLote>>({})
  const [errorBorrador, setErrorBorrador] = useState<Record<number, string>>({})
  const [enviandoLote, setEnviandoLote] = useState<number | null>(null)
  const [publicando, setPublicando] = useState<number | null>(null)
  const [errorPublicar, setErrorPublicar] = useState<Record<number, string>>({})
  const [loteEnEdicion, setLoteEnEdicion] = useState<number | null>(null)
  const [borradorEdicion, setBorradorEdicion] = useState<BorradorLote>(BORRADOR_VACIO)
  const [errorEdicion, setErrorEdicion] = useState<string | undefined>(undefined)
  const [guardandoEdicion, setGuardandoEdicion] = useState(false)
  const [eliminandoLote, setEliminandoLote] = useState<number | null>(null)
  const [avisoLote, setAvisoLote] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      setCargando(true)
      setError(null)
      try {
        const datos = await listarBandejaEmergencias({
          publicada: pestania === 'publicadas',
          pagina,
          por_pagina: POR_PAGINA,
        })
        if (!vigente) {
          return
        }
        setBandeja(datos)
        if (datos.paginas > 0 && datos.pagina > datos.paginas) {
          setPagina(datos.paginas)
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
  }, [pestania, pagina, recargo])

  function cambiarPestania(valor: PestaniaBandeja) {
    setPagina(1)
    setPestania(valor)
  }

  function alternar(emergenciaId: number) {
    setDesplegadas((actuales) => {
      const siguientes = new Set(actuales)
      if (siguientes.has(emergenciaId)) {
        siguientes.delete(emergenciaId)
      } else {
        siguientes.add(emergenciaId)
      }
      return siguientes
    })
  }

  function actualizarBorrador(
    emergenciaId: number,
    campo: keyof BorradorLote,
    valor: string,
  ) {
    setBorradores((actuales) => {
      const actual = actuales[emergenciaId] ?? BORRADOR_VACIO
      return { ...actuales, [emergenciaId]: { ...actual, [campo]: valor } }
    })
    setErrorBorrador((actuales) => sinClave(actuales, emergenciaId))
  }

  function actualizarLotesEnBandeja(
    emergenciaId: number,
    transformar: (emergencia: EmergenciaRead) => EmergenciaRead,
  ) {
    setBandeja((actual) => {
      if (actual === null) {
        return actual
      }
      return {
        ...actual,
        items: actual.items.map((emergencia) =>
          emergencia.id === emergenciaId ? transformar(emergencia) : emergencia,
        ),
      }
    })
  }

  async function manejarEnvioLote(
    evento: FormEvent<HTMLFormElement>,
    emergencia: EmergenciaRead,
  ) {
    evento.preventDefault()

    const borrador = borradores[emergencia.id] ?? BORRADOR_VACIO
    const tipo = borrador.tipo.trim()
    const cantidad = Number(borrador.cantidad)

    if (!tipo) {
      setErrorBorrador((actuales) => ({
        ...actuales,
        [emergencia.id]: 'Ingresá el tipo de lote.',
      }))
      return
    }
    if (!Number.isInteger(cantidad) || cantidad <= 0) {
      setErrorBorrador((actuales) => ({
        ...actuales,
        [emergencia.id]: 'La cantidad debe ser un número entero mayor a 0.',
      }))
      return
    }

    setEnviandoLote(emergencia.id)
    try {
      const creado = await crearLote(emergencia.id, {
        tipo,
        cantidad,
        unidad: borrador.unidad.trim() || null,
        descripcion: borrador.descripcion.trim() || null,
      })
      actualizarLotesEnBandeja(emergencia.id, (item) => ({
        ...item,
        lotes: [...item.lotes, creado],
      }))
      setErrorBorrador((actuales) => sinClave(actuales, emergencia.id))
      setBorradores((actuales) => sinClave(actuales, emergencia.id))
    } catch (fallo) {
      setErrorBorrador((actuales) => ({
        ...actuales,
        [emergencia.id]: describirError(fallo),
      }))
    } finally {
      setEnviandoLote(null)
    }
  }

  function abrirEdicionLote(lote: LoteNecesidad) {
    setLoteEnEdicion(lote.id)
    setBorradorEdicion({
      tipo: lote.tipo,
      cantidad: String(lote.cantidad),
      unidad: lote.unidad ?? '',
      descripcion: lote.descripcion ?? '',
    })
    setErrorEdicion(undefined)
    setAvisoLote(null)
  }

  function cerrarEdicionLote() {
    setLoteEnEdicion(null)
    setBorradorEdicion(BORRADOR_VACIO)
    setErrorEdicion(undefined)
  }

  function cambiarCampoEdicion(campo: keyof BorradorLote, valor: string) {
    setBorradorEdicion((actual) => ({ ...actual, [campo]: valor }))
    setErrorEdicion(undefined)
  }

  async function manejarEnvioEdicion(
    evento: FormEvent<HTMLFormElement>,
    lote: LoteNecesidad,
  ) {
    evento.preventDefault()

    const tipo = borradorEdicion.tipo.trim()
    const cantidad = Number(borradorEdicion.cantidad)

    if (!tipo) {
      setErrorEdicion('Ingresá el tipo de lote.')
      return
    }
    if (!Number.isInteger(cantidad) || cantidad <= 0) {
      setErrorEdicion('La cantidad debe ser un número entero mayor a 0.')
      return
    }

    setGuardandoEdicion(true)
    try {
      const actualizado = await actualizarLote(lote.id, {
        tipo,
        cantidad,
        unidad: borradorEdicion.unidad.trim() || null,
        descripcion: borradorEdicion.descripcion.trim() || null,
      })
      actualizarLotesEnBandeja(lote.emergencia_id, (item) => ({
        ...item,
        lotes: item.lotes.map((registro) =>
          registro.id === lote.id ? actualizado : registro,
        ),
      }))
      setAvisoLote(null)
      cerrarEdicionLote()
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.status === 409) {
        // La emergencia se publicó desde otra sesión: el lote ya no es editable.
        cerrarEdicionLote()
        setAvisoLote(describirError(fallo))
        setRecargo((actual) => actual + 1)
        return
      }
      setErrorEdicion(describirError(fallo))
    } finally {
      setGuardandoEdicion(false)
    }
  }

  async function manejarEliminar(lote: LoteNecesidad) {
    const confirmado = window.confirm(
      `¿Eliminar el lote "${lote.tipo}" (${lote.cantidad} ${lote.unidad ?? 'unidades'})? Esta acción no se puede deshacer.`,
    )
    if (!confirmado) {
      return
    }

    setEliminandoLote(lote.id)
    try {
      await eliminarLote(lote.id)
      actualizarLotesEnBandeja(lote.emergencia_id, (item) => ({
        ...item,
        lotes: item.lotes.filter((registro) => registro.id !== lote.id),
      }))
      setAvisoLote(null)
      if (loteEnEdicion === lote.id) {
        cerrarEdicionLote()
      }
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.status === 409) {
        // La emergencia se publicó o el lote ya tiene ofertas asociadas: recargamos la bandeja.
        setRecargo((actual) => actual + 1)
      }
      setAvisoLote(describirError(fallo))
    } finally {
      setEliminandoLote(null)
    }
  }

  async function manejarPublicar(emergencia: EmergenciaRead) {
    setPublicando(emergencia.id)
    try {
      await publicarEmergencia(emergencia.id)
      setErrorPublicar((actuales) => sinClave(actuales, emergencia.id))
      setRecargo((actual) => actual + 1)
    } catch (fallo) {
      setErrorPublicar((actuales) => ({
        ...actuales,
        [emergencia.id]: describirError(fallo),
      }))
    } finally {
      setPublicando(null)
    }
  }

  const totalPaginas = bandeja?.paginas ?? 0
  const paginaActual = bandeja?.pagina ?? pagina
  const sinPaginas = totalPaginas === 0
  const editable = pestania === 'sin_publicar'
  const tituloBandeja =
    PESTANIAS_BANDEJA.find((p) => p.valor === pestania)?.titulo ?? pestania

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">Centro coordinador</h2>
        <p className="text-sm text-slate-400">
          Bandeja de emergencias. Tocá una fila para desplegar su detalle, cargar sus
          lotes de necesidad y publicarla.
        </p>
      </div>

      <nav aria-label="Secciones del centro coordinador" className="flex flex-wrap gap-2">
        {PESTANIAS_BANDEJA.map((item) => (
          <button
            key={item.valor}
            type="button"
            aria-current={pestania === item.valor ? 'page' : undefined}
            onClick={() => cambiarPestania(item.valor)}
            className={clasePestania(pestania === item.valor)}
          >
            {item.etiqueta}
          </button>
        ))}
      </nav>

      <div className="rounded-xl bg-slate-800 border border-slate-700 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-cyan-400 mb-1">{tituloBandeja}</h2>
        <p className="text-sm text-slate-400">{DESCRIPCIONES_BANDEJA[pestania]}</p>
      </div>

      {avisoLote !== null && (
        <p role="alert" className={claseError}>
          {avisoLote}
        </p>
      )}

      {cargando && bandeja !== null && (
        <p className="text-sm text-slate-400">Actualizando la bandeja...</p>
      )}

      {cargando && bandeja === null && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando emergencias...
        </p>
      )}

      {!cargando && error !== null && (
        <p role="alert" className={claseError}>
          No se pudieron cargar las emergencias. {error}
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          {editable
            ? 'No hay emergencias sin publicar.'
            : 'Todavía no hay emergencias publicadas.'}
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {bandeja.items.map((emergencia) => {
            const desplegada = desplegadas.has(emergencia.id)
            const borrador = borradores[emergencia.id] ?? BORRADOR_VACIO
            const errorFormulario = errorBorrador[emergencia.id]
            const errorPublicacion = errorPublicar[emergencia.id]
            const guardandoLote = enviandoLote === emergencia.id

            return (
              <li
                key={emergencia.id}
                className="rounded-xl bg-slate-800 border border-slate-700 shadow-2xl"
              >
                <button
                  type="button"
                  onClick={() => alternar(emergencia.id)}
                  aria-expanded={desplegada}
                  aria-controls={idPanel(emergencia.id)}
                  className="flex w-full flex-col gap-3 p-4 text-left"
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-base font-semibold text-white">
                      {emergencia.zona_afectada}
                    </span>
                    <span className="font-mono text-xs text-slate-500">
                      #{emergencia.id}
                    </span>
                  </span>

                  <span className="flex flex-wrap gap-2">
                    <span
                      className={clasesDeGravedad(emergencia.nivel_gravedad)}
                    >
                      Gravedad: {etiquetaDeGravedad(emergencia.nivel_gravedad)}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                      Estado: {etiquetaDeEstado(emergencia.estado)}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                      Lotes: {emergencia.lotes.length}
                    </span>
                  </span>

                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-xs text-slate-400">
                      {editable ? 'Registrada el ' : 'Publicada el '}
                      {editable
                        ? formatearFecha(emergencia.fecha_hora_registro, 'Sin fecha')
                        : formatearFecha(emergencia.fecha_publicacion, 'Sin fecha')}
                    </span>
                    <span className="text-xs font-semibold text-cyan-400">
                      {desplegada ? 'Ocultar detalles ▾' : 'Ver detalles ▸'}
                    </span>
                  </span>
                </button>

                {desplegada && (
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <DetalleEmergencia emergencia={emergencia} />
                    <ListaLotes
                      lotes={emergencia.lotes}
                      editable={editable}
                      loteEnEdicion={loteEnEdicion}
                      borradorEdicion={borradorEdicion}
                      errorEdicion={errorEdicion}
                      guardandoEdicion={guardandoEdicion}
                      eliminandoLote={eliminandoLote}
                      alAbrirEdicion={abrirEdicionLote}
                      alCancelarEdicion={cerrarEdicionLote}
                      alCambiarCampoEdicion={cambiarCampoEdicion}
                      alEnviarEdicion={(evento, lote) =>
                        void manejarEnvioEdicion(evento, lote)
                      }
                      alEliminar={(lote) => void manejarEliminar(lote)}
                    />

                    {editable && (
                      <div className="flex flex-col gap-3">
                        <form
                          onSubmit={(evento) => void manejarEnvioLote(evento, emergencia)}
                          className="rounded-lg bg-slate-900 border border-slate-700 p-4 flex flex-col gap-3"
                          noValidate
                        >
                          <h4 className="text-sm font-bold text-cyan-400">
                            Agregar lote de necesidad
                          </h4>

                          <div>
                            <label
                              htmlFor={`lote-${emergencia.id}-tipo`}
                              className={claseEtiqueta}
                            >
                              Tipo
                            </label>
                            <input
                              id={`lote-${emergencia.id}-tipo`}
                              type="text"
                              value={borrador.tipo}
                              onChange={(evento) =>
                                actualizarBorrador(
                                  emergencia.id,
                                  'tipo',
                                  evento.target.value,
                                )
                              }
                              placeholder="Colchones"
                              maxLength={120}
                              required
                              className={claseCampo}
                            />
                          </div>

                          <div className="flex flex-wrap gap-3">
                            <div className="flex-1 min-w-32">
                              <label
                                htmlFor={`lote-${emergencia.id}-cantidad`}
                                className={claseEtiqueta}
                              >
                                Cantidad
                              </label>
                              <input
                                id={`lote-${emergencia.id}-cantidad`}
                                type="number"
                                min={1}
                                step={1}
                                value={borrador.cantidad}
                                onChange={(evento) =>
                                  actualizarBorrador(
                                    emergencia.id,
                                    'cantidad',
                                    evento.target.value,
                                  )
                                }
                                placeholder="50"
                                required
                                className={claseCampo}
                              />
                            </div>

                            <div className="flex-1 min-w-32">
                              <label
                                htmlFor={`lote-${emergencia.id}-unidad`}
                                className={claseEtiqueta}
                              >
                                Unidad (opcional)
                              </label>
                              <input
                                id={`lote-${emergencia.id}-unidad`}
                                type="text"
                                value={borrador.unidad}
                                onChange={(evento) =>
                                  actualizarBorrador(
                                    emergencia.id,
                                    'unidad',
                                    evento.target.value,
                                  )
                                }
                                placeholder="unidades"
                                maxLength={50}
                                className={claseCampo}
                              />
                            </div>
                          </div>

                          <div>
                            <label
                              htmlFor={`lote-${emergencia.id}-descripcion`}
                              className={claseEtiqueta}
                            >
                              Descripción (opcional)
                            </label>
                            <textarea
                              id={`lote-${emergencia.id}-descripcion`}
                              value={borrador.descripcion}
                              onChange={(evento) =>
                                actualizarBorrador(
                                  emergencia.id,
                                  'descripcion',
                                  evento.target.value,
                                )
                              }
                              placeholder="Detalle del lote, dónde se entrega, prioridad."
                              rows={2}
                              className={claseCampo}
                            />
                          </div>

                          {errorFormulario !== undefined && (
                            <p role="alert" className={claseError}>
                              {errorFormulario}
                            </p>
                          )}

                          <button
                            type="submit"
                            disabled={guardandoLote}
                            className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {guardandoLote ? 'Guardando lote...' : 'Agregar lote'}
                          </button>
                        </form>

                        <div className="rounded-lg bg-slate-900 border border-slate-700 p-4 flex flex-col gap-3">
                          {errorPublicacion !== undefined && (
                            <p role="alert" className={claseError}>
                              {errorPublicacion}
                            </p>
                          )}

                          <button
                            type="button"
                            onClick={() => void manejarPublicar(emergencia)}
                            disabled={
                              emergencia.lotes.length === 0 ||
                              publicando === emergencia.id
                            }
                            className="rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {publicando === emergencia.id
                              ? 'Publicando...'
                              : 'Publicar lotes'}
                          </button>

                          {emergencia.lotes.length === 0 && (
                            <p className="text-xs text-slate-400">
                              Carga al menos un lote de necesidad para poder publicar.
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!sinPaginas && (
        <nav
          aria-label="Paginación de la bandeja"
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <button
            type="button"
            onClick={() => setPagina((actual) => Math.max(1, actual - 1))}
            disabled={cargando || paginaActual <= 1}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Anterior
          </button>

          <p className="text-sm text-slate-400">
            Página {paginaActual} de {totalPaginas}
          </p>

          <button
            type="button"
            onClick={() => setPagina((actual) => actual + 1)}
            disabled={cargando || paginaActual >= totalPaginas}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Siguiente
          </button>
        </nav>
      )}
    </section>
  )
}
