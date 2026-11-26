import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  adjudicarOferta,
  confirmarSeleccionOfertas,
  listarBandejaEmergencias,
  listarOfertasDeEmergencia,
} from '../services'
import { PanelAdjudicacion } from '../components'
import { claseError, clasePestania, claseSubPanel } from '../ui/clases'
import type { BandaEmergencias, EmergenciaRead, LoteNecesidad, NivelGravedad } from '../types'
import type { OfertaCoordinadorRead } from '../types/oferta'
import {
  describirError,
  etiquetaDeEstado,
  etiquetaDeGravedad,
  formatearFecha,
} from '../utils/formato'

type PestaniaAdjudicacion = 'esperando_adjudicacion' | 'en_proceso'

const PESTANIAS: { valor: PestaniaAdjudicacion; etiqueta: string; titulo: string; descripcion: string }[] = [
  {
    valor: 'esperando_adjudicacion',
    etiqueta: 'Esperando adjudicación',
    titulo: 'Emergencias esperando adjudicación',
    descripcion: 'Seleccioná las ofertas validadas por el Sistema Nacional que mejor cubran las necesidades de la emergencia.',
  },
  {
    valor: 'en_proceso',
    etiqueta: 'En proceso',
    titulo: 'Emergencias en proceso',
    descripcion: 'Emergencias con ofertas adjudicadas y atención en curso.',
  },
]

const POR_PAGINA = 10

const CLASES_GRAVEDAD: Record<NivelGravedad, string> = {
  baja: 'rounded-full border border-emerald-500/50 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300',
  media: 'rounded-full border border-yellow-500/50 bg-yellow-500/10 px-2 py-0.5 text-xs text-yellow-300',
  alta: 'rounded-full border border-orange-500/50 bg-orange-500/10 px-2 py-0.5 text-xs text-orange-300',
  critica: 'rounded-full border border-red-500/50 bg-red-500/10 px-2 py-0.5 text-xs text-red-300',
}

function idPanel(emergenciaId: number): string {
  return `detalle-adjudicacion-${emergenciaId}`
}

function sinClave<T>(registro: Record<number, T>, clave: number): Record<number, T> {
  const siguiente = { ...registro }
  delete siguiente[clave]
  return siguiente
}

function DetalleEmergencia({ emergencia }: { emergencia: EmergenciaRead }) {
  return (
    <div id={idPanel(emergencia.id)} className={claseSubPanel}>
      <dl className="flex flex-col">
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Id</dt>
          <dd className="font-mono text-cyan-400">{emergencia.id}</dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Nivel de gravedad</dt>
          <dd className="font-mono text-cyan-400">{etiquetaDeGravedad(emergencia.nivel_gravedad)}</dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Zona afectada</dt>
          <dd className="font-mono text-cyan-400 break-all">{emergencia.zona_afectada}</dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Estado</dt>
          <dd className="font-mono text-cyan-400">{etiquetaDeEstado(emergencia.estado)}</dd>
        </div>
        <div className="flex justify-between gap-4 py-1">
          <dt className="text-slate-400">Registrada el</dt>
          <dd className="font-mono text-cyan-400">
            {formatearFecha(emergencia.fecha_hora_registro, 'Sin fecha')}
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

function ListaLotes({ lotes }: { lotes: LoteNecesidad[] }) {
  if (lotes.length === 0) {
    return <p className="text-sm text-slate-400">La emergencia no tiene lotes de necesidad cargados.</p>
  }

  return (
    <div className={claseSubPanel}>
      <p className="text-xs font-semibold text-slate-400">Lotes de necesidad ({lotes.length})</p>
      <ul className="mt-2 flex flex-col gap-2">
        {lotes.map((lote) => (
          <li key={lote.id} className="rounded-lg bg-slate-800 border border-slate-700 p-3 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold text-white">{lote.tipo}</span>
              <span className="font-mono text-cyan-400">
                {lote.cantidad} {lote.unidad ?? 'unidades'}
              </span>
            </div>
            {lote.descripcion !== null && (
              <p className="mt-1 whitespace-pre-wrap text-xs text-slate-400">{lote.descripcion}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

// Bandeja del operador municipal para seleccionar y adjudicar las ofertas que
// el Sistema Nacional ya validó.
export function AdjudicacionMunicipioPage() {
  const [pestania, setPestania] = useState<PestaniaAdjudicacion>('esperando_adjudicacion')
  const pestaniaActual = useRef<PestaniaAdjudicacion>('esperando_adjudicacion')
  const [pagina, setPagina] = useState(1)
  const [bandeja, setBandeja] = useState<BandaEmergencias | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recargo, setRecargo] = useState(0)
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())
  const [ofertasPorEmergencia, setOfertasPorEmergencia] = useState<Record<number, OfertaCoordinadorRead[]>>({})
  const [cargandoOfertas, setCargandoOfertas] = useState<Record<number, boolean>>({})
  const [errorOfertas, setErrorOfertas] = useState<Record<number, string>>({})
  const [adjudicando, setAdjudicando] = useState<Record<number, number>>({})
  const [errorAdjudicar, setErrorAdjudicar] = useState<Record<number, string>>({})
  const [exitoAdjudicar, setExitoAdjudicar] = useState<Record<number, string>>({})
  const [confirmando, setConfirmando] = useState<Record<number, boolean>>({})
  const [confirmadas, setConfirmadas] = useState<Record<number, boolean>>({})
  const [errorConfirmar, setErrorConfirmar] = useState<Record<number, string>>({})
  const [exitoConfirmar, setExitoConfirmar] = useState<Record<number, string>>({})
  const [confirmacionesAdjudicacion, setConfirmacionesAdjudicacion] = useState<Record<number, boolean>>({})
  const operacionesOfertas = useRef(new Set<number>())
  const adjudicadasRecientes = useRef(new Set<number>())
  const confirmadasRecientes = useRef(new Set<number>())
  const ofertasVigentes = useRef<Record<number, OfertaCoordinadorRead[]>>({})

  useEffect(() => {
    let vigente = true

    async function cargar() {
      setCargando(true)
      setError(null)
      try {
        const datos = await listarBandejaEmergencias({
          publicada: true,
          estado: pestania,
          ...(pestania === 'esperando_adjudicacion' ? { etapa_bonita: 'esperando_adjudicacion' as const } : {}),
          pagina,
          por_pagina: POR_PAGINA,
        })
        if (!vigente || pestaniaActual.current !== pestania) {
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

  function cambiarPestania(valor: PestaniaAdjudicacion) {
    pestaniaActual.current = valor
    setPagina(1)
    setPestania(valor)
    for (const emergenciaId of desplegadas) {
      if (ofertasVigentes.current[emergenciaId] === undefined) void cargarOfertasDeEmergencia(emergenciaId)
    }
  }

  async function cargarOfertasDeEmergencia(emergenciaId: number): Promise<boolean> {
    setCargandoOfertas((actuales) => ({ ...actuales, [emergenciaId]: true }))
    try {
      const ofertas = await listarOfertasDeEmergencia(emergenciaId)
      ofertasVigentes.current[emergenciaId] = ofertas
      setOfertasPorEmergencia((actuales) => ({ ...actuales, [emergenciaId]: ofertas }))
      setErrorOfertas((actuales) => sinClave(actuales, emergenciaId))
      return true
    } catch (fallo) {
      setErrorOfertas((actuales) => ({ ...actuales, [emergenciaId]: describirError(fallo) }))
      return false
    } finally {
      setCargandoOfertas((actuales) => ({ ...actuales, [emergenciaId]: false }))
    }
  }

  async function manejarAdjudicar(
    emergenciaId: number,
    ofertaId: number,
    paraSeleccion: boolean,
  ): Promise<void> {
    const ofertas = ofertasVigentes.current[emergenciaId]
    const oferta = ofertas?.find((registro) => registro.id === ofertaId)
    if (
      pestaniaActual.current !== 'esperando_adjudicacion' || oferta === undefined ||
      operacionesOfertas.current.has(emergenciaId) ||
      confirmadasRecientes.current.has(emergenciaId) ||
      (paraSeleccion && !oferta.puede_seleccionar) ||
      oferta.adjudicada_en !== null || adjudicadasRecientes.current.has(ofertaId) ||
      (!paraSeleccion && ofertas?.some((registro) =>
        registro.adjudicada_en !== null || adjudicadasRecientes.current.has(registro.id),
      ))
    ) return

    operacionesOfertas.current.add(emergenciaId)
    setAdjudicando((actuales) => ({ ...actuales, [emergenciaId]: ofertaId }))
    setErrorAdjudicar((actuales) => sinClave(actuales, ofertaId))
    setExitoAdjudicar((actuales) => sinClave(actuales, ofertaId))
    try {
      const respuesta = await adjudicarOferta(ofertaId, paraSeleccion)
      if (respuesta?.oferta_id !== ofertaId || typeof respuesta.mensaje !== 'string') {
        throw new ApiError(200, 'La respuesta de adjudicación no pudo verificarse.')
      }
      adjudicadasRecientes.current.add(ofertaId)
      setExitoAdjudicar((actuales) => ({ ...actuales, [ofertaId]: respuesta.mensaje }))
      await cargarOfertasDeEmergencia(emergenciaId)
      if (!paraSeleccion) {
        cambiarPestania('en_proceso')
        setRecargo((actual) => actual + 1)
      }
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.status === 409) {
        await cargarOfertasDeEmergencia(emergenciaId)
        setRecargo((actual) => actual + 1)
      }
      setErrorAdjudicar((actuales) => ({ ...actuales, [ofertaId]: describirError(fallo) }))
    } finally {
      operacionesOfertas.current.delete(emergenciaId)
      setAdjudicando((actuales) => sinClave(actuales, emergenciaId))
      setConfirmacionesAdjudicacion((actuales) => sinClave(actuales, ofertaId))
    }
  }

  function solicitarConfirmacionAdjudicacion(ofertaId: number) {
    setConfirmacionesAdjudicacion((actuales) => ({ ...actuales, [ofertaId]: true }))
  }

  function cancelarConfirmacionAdjudicacion(ofertaId: number) {
    setConfirmacionesAdjudicacion((actuales) => sinClave(actuales, ofertaId))
  }

  function confirmarAdjudicacionSoloOferta(emergenciaId: number, ofertaId: number) {
    setConfirmacionesAdjudicacion((actuales) => sinClave(actuales, ofertaId))
    void manejarAdjudicar(emergenciaId, ofertaId, false)
  }

  async function manejarConfirmarSeleccion(emergenciaId: number): Promise<void> {
    const ofertas = ofertasVigentes.current[emergenciaId]
    if (
      (pestaniaActual.current !== 'esperando_adjudicacion' && pestaniaActual.current !== 'en_proceso') ||
      operacionesOfertas.current.has(emergenciaId) || confirmadasRecientes.current.has(emergenciaId) ||
      !ofertas?.some((oferta) => oferta.adjudicada_en !== null || adjudicadasRecientes.current.has(oferta.id))
    ) return

    operacionesOfertas.current.add(emergenciaId)
    setConfirmando((actuales) => ({ ...actuales, [emergenciaId]: true }))
    setErrorConfirmar((actuales) => sinClave(actuales, emergenciaId))
    try {
      const respuesta = await confirmarSeleccionOfertas(emergenciaId)
      if (respuesta?.emergencia_id !== emergenciaId || typeof respuesta.ya_confirmada !== 'boolean') {
        throw new ApiError(200, 'La respuesta de confirmación no pudo verificarse.')
      }
      confirmadasRecientes.current.add(emergenciaId)
      setConfirmadas((actuales) => ({ ...actuales, [emergenciaId]: true }))
      setExitoAdjudicar((actuales) => {
        const siguientes = { ...actuales }
        for (const oferta of ofertas) delete siguientes[oferta.id]
        return siguientes
      })
      setExitoConfirmar((actuales) => ({
        ...actuales,
        [emergenciaId]: respuesta.ya_confirmada
          ? 'La selección ya estaba confirmada.'
          : 'Selección confirmada correctamente.',
      }))
      await cargarOfertasDeEmergencia(emergenciaId)
      cambiarPestania('en_proceso')
      setRecargo((actual) => actual + 1)
    } catch (fallo) {
      setErrorConfirmar((actuales) => ({ ...actuales, [emergenciaId]: describirError(fallo) }))
    } finally {
      operacionesOfertas.current.delete(emergenciaId)
      setConfirmando((actuales) => sinClave(actuales, emergenciaId))
    }
  }

  function alternar(emergenciaId: number) {
    const desplegando = !desplegadas.has(emergenciaId)

    setDesplegadas((actuales) => {
      const siguientes = new Set(actuales)
      if (siguientes.has(emergenciaId)) {
        siguientes.delete(emergenciaId)
      } else {
        siguientes.add(emergenciaId)
      }
      return siguientes
    })

    if (desplegando && ofertasPorEmergencia[emergenciaId] === undefined) {
      void cargarOfertasDeEmergencia(emergenciaId)
    }
  }

  const totalPaginas = bandeja?.paginas ?? 0
  const paginaActual = bandeja?.pagina ?? pagina
  const sinPaginas = totalPaginas === 0
  const seccion = PESTANIAS.find((item) => item.valor === pestania) ?? PESTANIAS[0]

  return (
    <section className="flex flex-col gap-4">
      <nav aria-label="Secciones de adjudicación" className="flex flex-wrap gap-2">
        {PESTANIAS.map((item) => (
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
        <h2 className="text-xl font-bold text-cyan-400 mb-1">{seccion.titulo}</h2>
        <p className="text-sm text-slate-400">{seccion.descripcion}</p>
        {pestania === 'esperando_adjudicacion' && (
          <p className="text-sm text-slate-400">
            Solo aparecen las emergencias que el proceso habilitó para adjudicar. Si la cobertura no alcanzó, primero decide el Centro Coordinador.
          </p>
        )}
      </div>

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
          No hay emergencias en este estado.
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {bandeja.items.map((emergencia) => {
            const desplegada = desplegadas.has(emergencia.id)

            return (
              <li key={emergencia.id} className="rounded-xl bg-slate-800 border border-slate-700 shadow-2xl">
                <button
                  type="button"
                  onClick={() => alternar(emergencia.id)}
                  aria-expanded={desplegada}
                  aria-controls={idPanel(emergencia.id)}
                  className="flex w-full flex-col gap-3 p-4 text-left"
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-base font-semibold text-white">{emergencia.zona_afectada}</span>
                    <span className="font-mono text-xs text-slate-500">#{emergencia.id}</span>
                  </span>

                  <span className="flex flex-wrap gap-2">
                    <span className={CLASES_GRAVEDAD[emergencia.nivel_gravedad]}>
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
                      Publicada el {formatearFecha(emergencia.fecha_publicacion, 'Sin fecha')}
                    </span>
                    <span className="text-xs font-semibold text-cyan-400">
                      {desplegada ? 'Ocultar detalles ▾' : 'Ver detalles ▸'}
                    </span>
                  </span>
                </button>

                {desplegada && (
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <DetalleEmergencia emergencia={emergencia} />
                    <ListaLotes lotes={emergencia.lotes} />
                    <PanelAdjudicacion
                      titulo="Ofertas validadas"
                      mensajeSinOfertas="Todavía no hay ofertas validadas por el Sistema Nacional para esta emergencia."
                      etiquetaVerificada="Verificado por el Sistema Nacional"
                      ofertas={ofertasPorEmergencia[emergencia.id]}
                      lotes={emergencia.lotes}
                      cargando={cargandoOfertas[emergencia.id] === true}
                      errorCarga={errorOfertas[emergencia.id]}
                      adjudicando={adjudicando[emergencia.id] ?? null}
                      errorAdjudicar={errorAdjudicar}
                      exitoAdjudicar={exitoAdjudicar}
                      alAdjudicar={(ofertaId, paraSeleccion) => void manejarAdjudicar(emergencia.id, ofertaId, paraSeleccion)}
                      confirmando={confirmando[emergencia.id] === true}
                      confirmada={confirmadas[emergencia.id] === true}
                      errorConfirmar={errorConfirmar[emergencia.id]}
                      exitoConfirmar={exitoConfirmar[emergencia.id]}
                      confirmacionesPendientes={confirmacionesAdjudicacion}
                      alSolicitarConfirmacion={solicitarConfirmacionAdjudicacion}
                      alCancelarConfirmacion={cancelarConfirmacionAdjudicacion}
                      alConfirmarAdjudicacion={(ofertaId) => confirmarAdjudicacionSoloOferta(emergencia.id, ofertaId)}
                      alConfirmar={() => void manejarConfirmarSeleccion(emergencia.id)}
                      puedeAdjudicar={pestania === 'esperando_adjudicacion'}
                      puedeConfirmar={pestania === 'esperando_adjudicacion'}
                    />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!sinPaginas && (
        <nav aria-label="Paginación de adjudicación" className="flex flex-wrap items-center justify-between gap-3">
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
