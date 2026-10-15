import { useEffect, useState } from 'react'
import {
  listarEmergencias,
  listarLotes,
  listarOfertasDeOrganizacion,
  obtenerOfertasConsolidadas,
} from '../services'
import {
  claseBadge,
  claseBadgeAcento,
  claseBadgeAviso,
  claseBotonPrimario,
  claseCard,
  claseError,
  claseSubPanel,
  claseSubtitulo,
  claseTitulo,
} from '../ui/clases'
import {
  convocatoriaAbierta,
  describirError,
  etiquetaDeEstado,
  etiquetaDeGravedad,
  formatearFecha,
  tiempoRestante,
} from '../utils/formato'
import { FormularioOfertaPage } from './FormularioOfertaPage'
import type {
  EmergenciaRead,
  LoteRead,
  OfertaRead,
  OfertasConsolidadas,
} from '../types'

interface Props {
  organizacionId: number
}

interface DetalleConvocatoria {
  lotes: LoteRead[]
  consolidadas: OfertasConsolidadas | null
  cargando: boolean
  error: string | null
}

function idPanel(emergenciaId: number): string {
  return `detalle-convocatoria-${emergenciaId}`
}

/** Suma lo que toda la red ya ofertó para un lote. */
function totalOfrecidoDelLote(
  consolidadas: OfertasConsolidadas | null,
  loteId: number,
): number {
  if (consolidadas === null) {
    return 0
  }
  return consolidadas.ofertas.reduce(
    (suma, oferta) =>
      suma +
      oferta.items
        .filter((item) => item.lote_id === loteId)
        .reduce((parcial, item) => parcial + item.cantidad_ofrecida, 0),
    0,
  )
}

function LotesDeConvocatoria({
  emergenciaId,
  detalle,
}: {
  emergenciaId: number
  detalle: DetalleConvocatoria | undefined
}) {
  if (detalle === undefined || detalle.cargando) {
    return (
      <p id={idPanel(emergenciaId)} className={claseSubPanel}>
        <span className="text-slate-400">Cargando lotes de necesidad...</span>
      </p>
    )
  }

  if (detalle.error !== null) {
    return (
      <p id={idPanel(emergenciaId)} role="alert" className={claseError}>
        No se pudieron cargar los lotes. {detalle.error}
      </p>
    )
  }

  if (detalle.lotes.length === 0) {
    return (
      <p id={idPanel(emergenciaId)} className={claseSubPanel}>
        <span className="text-slate-400">
          Esta convocatoria todavía no tiene lotes de necesidad publicados.
        </span>
      </p>
    )
  }

  return (
    <div id={idPanel(emergenciaId)} className={claseSubPanel}>
      <p className="text-xs font-semibold text-slate-400">
        Lotes de necesidad
      </p>

      <ul className="mt-2 flex flex-col gap-3">
        {detalle.lotes.map((lote) => {
          const ofrecido = totalOfrecidoDelLote(detalle.consolidadas, lote.id)
          const cubierto = Math.min(
            100,
            Math.round((ofrecido / lote.cantidad) * 100),
          )

          return (
            <li
              key={lote.id}
              className="border-t border-slate-700 pt-3 first:border-t-0 first:pt-0"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold text-white">{lote.tipo}</span>
                <span className="font-mono text-xs text-cyan-400">
                  {ofrecido} / {lote.cantidad}
                  {lote.unidad ? ` ${lote.unidad}` : ''}
                </span>
              </div>

              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className={
                    cubierto >= 100 ? 'h-full bg-emerald-400' : 'h-full bg-cyan-500'
                  }
                  style={{ width: `${cubierto}%` }}
                />
              </div>

              <p className="mt-1 text-xs text-slate-400">
                {cubierto >= 100
                  ? 'La red ya cubrió lo requerido'
                  : `Cubierto por la red: ${cubierto}%`}
                {lote.descripcion ? ` · ${lote.descripcion}` : ''}
              </p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function ConvocatoriasPage({ organizacionId }: Props) {
  const [convocatorias, setConvocatorias] = useState<EmergenciaRead[]>([])
  const [misOfertas, setMisOfertas] = useState<OfertaRead[]>([])
  const [detalles, setDetalles] = useState<Record<number, DetalleConvocatoria>>({})
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())
  const [seleccionada, setSeleccionada] = useState<EmergenciaRead | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recargas, setRecargas] = useState(0)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const [emergencias, ofertas] = await Promise.all([
          listarEmergencias(),
          listarOfertasDeOrganizacion(organizacionId),
        ])
        if (!vigente) return
        setError(null)
        setConvocatorias(emergencias.filter(convocatoriaAbierta))
        setMisOfertas(ofertas)
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

  async function cargarDetalle(emergenciaId: number) {
    setDetalles((actuales) => ({
      ...actuales,
      [emergenciaId]: {
        lotes: [],
        consolidadas: null,
        cargando: true,
        error: null,
      },
    }))

    try {
      const [lotes, consolidadas] = await Promise.all([
        listarLotes(emergenciaId),
        obtenerOfertasConsolidadas(emergenciaId),
      ])
      setDetalles((actuales) => ({
        ...actuales,
        [emergenciaId]: { lotes, consolidadas, cargando: false, error: null },
      }))
    } catch (fallo) {
      setDetalles((actuales) => ({
        ...actuales,
        [emergenciaId]: {
          lotes: [],
          consolidadas: null,
          cargando: false,
          error: describirError(fallo),
        },
      }))
    }
  }

  function alternar(emergenciaId: number) {
    setDesplegadas((actuales) => {
      const siguientes = new Set(actuales)
      if (siguientes.has(emergenciaId)) {
        siguientes.delete(emergenciaId)
      } else {
        siguientes.add(emergenciaId)
        if (detalles[emergenciaId] === undefined) {
          void cargarDetalle(emergenciaId)
        }
      }
      return siguientes
    })
  }

  function ofertaDeEmergencia(emergenciaId: number): OfertaRead | null {
    return (
      misOfertas.find((oferta) => oferta.emergencia_id === emergenciaId) ?? null
    )
  }

  function volverDelFormulario(huboCambios: boolean) {
    const emergenciaId = seleccionada?.id
    setSeleccionada(null)
    if (huboCambios) {
      setRecargas((actuales) => actuales + 1)
      if (emergenciaId !== undefined) {
        void cargarDetalle(emergenciaId)
      }
    }
  }

  if (seleccionada !== null) {
    return (
      <FormularioOfertaPage
        organizacionId={organizacionId}
        emergencia={seleccionada}
        ofertaExistente={ofertaDeEmergencia(seleccionada.id)}
        onVolver={volverDelFormulario}
      />
    )
  }

  return (
    <section className="flex flex-col gap-4">
      <div className={claseCard}>
        <h2 className={claseTitulo}>Convocatorias activas</h2>
        <p className={claseSubtitulo}>
          Emergencias publicadas que están recibiendo ofertas de ayuda. Tocá una
          convocatoria para ver sus lotes de necesidad y cuánto lleva cubierto la red.
        </p>
      </div>

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando convocatorias...
        </p>
      )}

      {!cargando && error !== null && (
        <p role="alert" className={claseError}>
          No se pudieron cargar las convocatorias. {error}
        </p>
      )}

      {!cargando && error === null && convocatorias.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          No hay convocatorias abiertas en este momento.
        </p>
      )}

      {!cargando && error === null && convocatorias.length > 0 && (
        <ul className="flex flex-col gap-3">
          {convocatorias.map((emergencia) => {
            const desplegada = desplegadas.has(emergencia.id)
            const miOferta = ofertaDeEmergencia(emergencia.id)
            const restante = tiempoRestante(emergencia)

            return (
              <li
                key={emergencia.id}
                className="group rounded-xl bg-slate-800 border border-slate-700 shadow-2xl transition hover:border-cyan-400"
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
                    <span className={claseBadge}>
                      Gravedad: {etiquetaDeGravedad(emergencia.nivel_gravedad)}
                    </span>
                    <span className={claseBadge}>
                      Estado: {etiquetaDeEstado(emergencia.estado)}
                    </span>
                    {restante !== null && (
                      <span className={claseBadgeAviso}>{restante}</span>
                    )}
                    {miOferta !== null && (
                      <span className={claseBadgeAcento}>Ya postulaste</span>
                    )}
                  </span>

                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-xs text-slate-400">
                      Publicada el{' '}
                      {formatearFecha(
                        emergencia.fecha_publicacion,
                        'Sin fecha de publicación',
                      )}
                    </span>
                    <span className="text-xs font-semibold text-cyan-400">
                      {desplegada ? 'Ocultar detalles ▾' : 'Ver detalles ▸'}
                    </span>
                  </span>
                </button>

                {desplegada && (
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <div className={claseSubPanel}>
                      <p className="text-xs font-semibold text-slate-400">
                        Descripción inicial
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
                        {emergencia.descripcion_inicial}
                      </p>
                    </div>

                    <LotesDeConvocatoria
                      emergenciaId={emergencia.id}
                      detalle={detalles[emergencia.id]}
                    />

                    <button
                      type="button"
                      onClick={() => setSeleccionada(emergencia)}
                      className={claseBotonPrimario}
                    >
                      {miOferta !== null
                        ? 'Editar mi oferta'
                        : 'Postular recursos'}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
