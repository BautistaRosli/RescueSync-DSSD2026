import { useEffect, useState } from 'react'
import {
  finalizarItemOferta,
  listarEmergencias,
  listarLotes,
  listarOfertasDeOrganizacion,
} from '../services'
import {
  claseBadge,
  claseBadgeAcento,
  claseBadgeExito,
  claseBotonPrimario,
  claseBotonSecundario,
  claseCard,
  claseError,
  claseSubPanel,
  claseSubtitulo,
  claseTitulo,
} from '../ui/clases'
import {
  convocatoriaAbierta,
  describirError,
  formatearFecha,
} from '../utils/formato'
import { FormularioOfertaPage } from './FormularioOfertaPage'
import type { EmergenciaRead, LoteRead, OfertaRead } from '../types'

interface Props {
  organizacionId: number
}

function idPanel(ofertaId: number): string {
  return `detalle-oferta-${ofertaId}`
}

export function MisOfertasPage({ organizacionId }: Props) {
  const [ofertas, setOfertas] = useState<OfertaRead[]>([])
  const [emergencias, setEmergencias] = useState<Record<number, EmergenciaRead>>({})
  const [lotes, setLotes] = useState<Record<number, LoteRead>>({})
  const [finalizando, setFinalizando] = useState<number | null>(null)
  const [errorFinalizar, setErrorFinalizar] = useState<Record<number, string>>({})
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())
  const [enEdicion, setEnEdicion] = useState<OfertaRead | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recargas, setRecargas] = useState(0)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const [misOfertas, todasLasEmergencias] = await Promise.all([
          listarOfertasDeOrganizacion(organizacionId),
          listarEmergencias(),
        ])

        const porId: Record<number, EmergenciaRead> = {}
        for (const emergencia of todasLasEmergencias) {
          porId[emergencia.id] = emergencia
        }

        const emergenciasDeOfertas = [
          ...new Set(misOfertas.map((oferta) => oferta.emergencia_id)),
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

        if (!vigente) return
        setError(null)
        setOfertas(misOfertas)
        setEmergencias(porId)
        setLotes(lotesPorId)
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

  function alternar(ofertaId: number) {
    setDesplegadas((actuales) => {
      const siguientes = new Set(actuales)
      if (siguientes.has(ofertaId)) {
        siguientes.delete(ofertaId)
      } else {
        siguientes.add(ofertaId)
      }
      return siguientes
    })
  }

  async function finalizarActividad(ofertaId: number, itemId: number) {
    setFinalizando(itemId)
    try {
      const itemFinalizado = await finalizarItemOferta(ofertaId, itemId)
      setErrorFinalizar((actuales) => {
        const siguientes = { ...actuales }
        delete siguientes[itemId]
        return siguientes
      })
      setOfertas((actuales) =>
        actuales.map((oferta) =>
          oferta.id === ofertaId
            ? {
                ...oferta,
                items: oferta.items.map((item) =>
                  item.id === itemId ? itemFinalizado : item,
                ),
              }
            : oferta,
        ),
      )
    } catch (fallo) {
      setErrorFinalizar((actuales) => ({
        ...actuales,
        [itemId]: describirError(fallo),
      }))
    } finally {
      setFinalizando(null)
    }
  }

  function nombreDeLote(loteId: number): string {
    return lotes[loteId]?.tipo ?? `Lote #${loteId}`
  }

  function volverDeEdicion(huboCambios: boolean) {
    setEnEdicion(null)
    if (huboCambios) {
      setRecargas((actuales) => actuales + 1)
    }
  }

  if (enEdicion !== null) {
    const emergencia = emergencias[enEdicion.emergencia_id]
    if (emergencia !== undefined) {
      return (
        <FormularioOfertaPage
          organizacionId={organizacionId}
          emergencia={emergencia}
          ofertaExistente={enEdicion}
          onVolver={volverDeEdicion}
        />
      )
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className={claseCard}>
        <h2 className={claseTitulo}>Mis ofertas</h2>
        <p className={claseSubtitulo}>
          Postulaciones de tu organización, incluidos los consorcios en los que
          participás. Podés modificarlas mientras la convocatoria siga abierta y
          marcar tus actividades como finalizadas.
        </p>
      </div>

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando tus ofertas...
        </p>
      )}

      {!cargando && error !== null && (
        <p role="alert" className={claseError}>
          No se pudieron cargar las ofertas. {error}
        </p>
      )}

      {!cargando && error === null && ofertas.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Todavía no postulaste recursos a ninguna convocatoria.
        </p>
      )}

      {!cargando && error === null && ofertas.length > 0 && (
        <ul className="flex flex-col gap-3">
          {ofertas.map((oferta) => {
            const desplegada = desplegadas.has(oferta.id)
            const emergencia = emergencias[oferta.emergencia_id]
            const abierta =
              emergencia !== undefined && convocatoriaAbierta(emergencia)
            const finalizadas = oferta.items.filter(
              (item) => item.finalizado_en !== null,
            ).length
            const esLider = oferta.organizacion_id === organizacionId

            return (
              <li
                key={oferta.id}
                className="group rounded-xl bg-slate-800 border border-slate-700 shadow-2xl transition hover:border-cyan-400"
              >
                <button
                  type="button"
                  onClick={() => alternar(oferta.id)}
                  aria-expanded={desplegada}
                  aria-controls={idPanel(oferta.id)}
                  className="flex w-full flex-col gap-3 p-4 text-left"
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-base font-semibold text-white">
                      {emergencia?.zona_afectada ??
                        `Emergencia #${oferta.emergencia_id}`}
                    </span>
                    <span className="font-mono text-xs text-slate-500">
                      Oferta #{oferta.id}
                    </span>
                  </span>

                  <span className="flex flex-wrap gap-2">
                    <span className={claseBadge}>
                      Lotes cubiertos: {oferta.items.length}
                    </span>
                    <span className={claseBadge}>
                      {abierta ? 'Convocatoria abierta' : 'Convocatoria cerrada'}
                    </span>
                    {oferta.es_conjunta && (
                      <span className={claseBadgeAcento}>Consorcio</span>
                    )}
                    {!esLider && (
                      <span className={claseBadge}>Participás como socia</span>
                    )}
                    {finalizadas > 0 && (
                      <span className={claseBadgeExito}>
                        {finalizadas} de {oferta.items.length} finalizadas
                      </span>
                    )}
                    {oferta.adjudicada_en !== null && (
                      <span className={claseBadgeExito}>
                        Adjudicada el{' '}
                        {formatearFecha(oferta.adjudicada_en, 'Sin fecha')}
                      </span>
                    )}
                  </span>

                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-xs text-slate-400">
                      Postulada el{' '}
                      {formatearFecha(oferta.fecha_hora_oferta, 'Sin fecha')}
                    </span>
                    <span className="text-xs font-semibold text-cyan-400">
                      {desplegada ? 'Ocultar detalles ▾' : 'Ver detalles ▸'}
                    </span>
                  </span>
                </button>

                {desplegada && (
                  <div
                    id={idPanel(oferta.id)}
                    className="flex flex-col gap-3 px-4 pb-4"
                  >
                    {oferta.es_conjunta && (
                      <div className={claseSubPanel}>
                        <p className="text-xs font-semibold text-slate-400">
                          Organizaciones del consorcio
                        </p>
                        <p className="mt-1 text-sm text-slate-300">
                          {oferta.organizaciones
                            .map((organizacion) => organizacion.nombre)
                            .join(' · ')}
                        </p>
                      </div>
                    )}

                    <div className={claseSubPanel}>
                      <p className="text-xs font-semibold text-slate-400">
                        Recursos ofertados y actividades
                      </p>

                      <ul className="mt-2 flex flex-col gap-3">
                        {oferta.items.map((item) => {
                          const lote = lotes[item.lote_necesidad_id]

                          return (
                            <li
                              key={item.id}
                              className="border-t border-slate-700 pt-3 first:border-t-0 first:pt-0"
                            >
                              <div className="flex flex-wrap items-baseline justify-between gap-2">
                                <span className="font-semibold text-white">
                                  {nombreDeLote(item.lote_necesidad_id)}
                                </span>
                                <span className="font-mono text-xs text-cyan-400">
                                  {item.cantidad_ofrecida}
                                  {lote?.unidad ? ` ${lote.unidad}` : ''}
                                  {lote ? ` de ${lote.cantidad} requeridos` : ''}
                                </span>
                              </div>

                              {item.descripcion && (
                                <p className="mt-1 text-xs text-slate-400">
                                  {item.descripcion}
                                </p>
                              )}

                              <div className="mt-2">
                                {item.finalizado_en !== null ? (
                                  <span className={claseBadgeExito}>
                                    Finalizada el{' '}
                                    {formatearFecha(
                                      item.finalizado_en,
                                      'Sin fecha',
                                    )}
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void finalizarActividad(oferta.id, item.id)
                                    }
                                    disabled={finalizando === item.id}
                                    className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-emerald-400 hover:text-emerald-400"
                                  >
                                    {finalizando === item.id
                                      ? 'Finalizando...'
                                      : 'Marcar actividad como finalizada'}
                                  </button>
                                )}

                                {errorFinalizar[item.id] !== undefined && (
                                  <p role="alert" className={claseError}>
                                    {errorFinalizar[item.id]}
                                  </p>
                                )}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    </div>

                    {oferta.observaciones && (
                      <div className={claseSubPanel}>
                        <p className="text-xs font-semibold text-slate-400">
                          Observaciones
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">
                          {oferta.observaciones}
                        </p>
                      </div>
                    )}

                    {abierta ? (
                      <button
                        type="button"
                        onClick={() => setEnEdicion(oferta)}
                        className={claseBotonPrimario}
                      >
                        Editar oferta
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled
                        className={claseBotonSecundario}
                      >
                        La ventana de convocatoria está cerrada
                      </button>
                    )}
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
