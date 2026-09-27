import { useEffect, useState } from 'react'
import {
  listarEmergencias,
  listarLotes,
  listarNotificaciones,
  listarOfertasDeOrganizacion,
  marcarLeida,
  simularAdjudicacion,
} from '../services'
import {
  claseAviso,
  claseBadge,
  claseBadgeAviso,
  claseBotonSecundario,
  claseCard,
  claseError,
  claseSubPanel,
  claseSubtitulo,
  claseTitulo,
} from '../ui/clases'
import { describirError, formatearFecha } from '../utils/formato'
import type {
  EmergenciaRead,
  LoteRead,
  NotificacionAdjudicacion,
  OfertaRead,
} from '../types'

interface Props {
  organizacionId: number
}

export function NotificacionesPage({ organizacionId }: Props) {
  const [notificaciones, setNotificaciones] = useState<
    NotificacionAdjudicacion[]
  >([])
  const [ofertas, setOfertas] = useState<OfertaRead[]>([])
  const [emergencias, setEmergencias] = useState<Record<number, EmergenciaRead>>({})
  const [lotes, setLotes] = useState<Record<number, LoteRead>>({})
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true

    async function cargar() {
      try {
        const [recibidas, misOfertas, todasLasEmergencias] = await Promise.all([
          listarNotificaciones(organizacionId),
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
        setNotificaciones(recibidas)
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
  }, [organizacionId])

  async function leer(notificacionId: number) {
    await marcarLeida(organizacionId, notificacionId)
    setNotificaciones((actuales) =>
      actuales.map((notificacion) =>
        notificacion.id === notificacionId
          ? { ...notificacion, leida: true }
          : notificacion,
      ),
    )
  }

  async function simular() {
    setError(null)
    const oferta = ofertas[0]
    if (oferta === undefined) {
      setError(
        'Para simular una adjudicación primero tenés que postular recursos a una convocatoria.',
      )
      return
    }
    try {
      const notificacion = await simularAdjudicacion(organizacionId, {
        ofertaId: oferta.id,
        emergenciaId: oferta.emergencia_id,
        zonaAfectada:
          emergencias[oferta.emergencia_id]?.zona_afectada ??
          `Emergencia #${oferta.emergencia_id}`,
        lotesAdjudicados: oferta.items.map(
          (item) =>
            lotes[item.lote_necesidad_id]?.tipo ??
            `Lote #${item.lote_necesidad_id}`,
        ),
      })
      setNotificaciones((actuales) => [notificacion, ...actuales])
    } catch (fallo) {
      setError(describirError(fallo))
    }
  }

  const sinLeer = notificaciones.filter(
    (notificacion) => !notificacion.leida,
  ).length

  return (
    <section className="flex flex-col gap-4">
      <div className={claseCard}>
        <h2 className={claseTitulo}>Notificaciones de adjudicación</h2>
        <p className={claseSubtitulo}>
          Avisos formales de las emergencias en las que tu propuesta fue
          seleccionada como responsable.
          {sinLeer > 0 ? ` Tenés ${sinLeer} sin leer.` : ''}
        </p>
      </div>

      <p className={claseAviso}>
        El módulo de adjudicación del municipio todavía no existe: estas
        notificaciones se generan y guardan solo en este navegador.
      </p>

      <button type="button" onClick={() => void simular()} className={claseBotonSecundario}>
        Simular adjudicación (demo)
      </button>

      {error !== null && (
        <p role="alert" className={claseError}>
          {error}
        </p>
      )}

      {cargando && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          Cargando notificaciones...
        </p>
      )}

      {!cargando && notificaciones.length === 0 && (
        <p className="rounded-xl bg-slate-800 border border-slate-700 p-6 text-sm text-slate-400 shadow-2xl">
          No tenés notificaciones de adjudicación.
        </p>
      )}

      {!cargando && notificaciones.length > 0 && (
        <ul className="flex flex-col gap-3">
          {notificaciones.map((notificacion) => (
            <li
              key={notificacion.id}
              className="rounded-xl bg-slate-800 border border-slate-700 p-4 shadow-2xl"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-base font-semibold text-white">
                  Adjudicación en {notificacion.zona_afectada}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  Oferta #{notificacion.oferta_id}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap gap-2">
                <span
                  className={notificacion.leida ? claseBadge : claseBadgeAviso}
                >
                  {notificacion.leida ? 'Leída' : 'No leída'}
                </span>
                <span className={claseBadge}>
                  {formatearFecha(notificacion.fecha_hora, 'Sin fecha')}
                </span>
              </div>

              <div className={`mt-3 ${claseSubPanel}`}>
                <p className="text-xs font-semibold text-slate-400">
                  Lotes adjudicados
                </p>
                <p className="mt-1 text-sm text-slate-300">
                  {notificacion.lotes_adjudicados.length > 0
                    ? notificacion.lotes_adjudicados.join(' · ')
                    : 'Sin detalle de lotes'}
                </p>
              </div>

              {!notificacion.leida && (
                <button
                  type="button"
                  onClick={() => void leer(notificacion.id)}
                  className="mt-3 rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400"
                >
                  Marcar como leída
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
