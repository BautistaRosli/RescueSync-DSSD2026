import {
  claseBadge,
  claseBotonSecundario,
  claseError,
  claseExito,
  claseSubPanel,
} from '../ui/clases'
import type { LoteNecesidad } from '../types'
import type { OfertaCoordinadorRead } from '../types/oferta'
import { formatearFecha } from '../utils/formato'
import { estaAdjudicadaParaCierre, puedeCerrarOferta } from '../utils/ofertas'

const SIN_MENSAJES: Record<number, string> = {}
const sinAccion = () => {}

export interface PanelAdjudicacionProps {
  ofertas: OfertaCoordinadorRead[] | undefined
  lotes: LoteNecesidad[]
  cargando: boolean
  errorCarga: string | undefined
  titulo?: string
  mensajeSinOfertas?: string
  etiquetaVerificada?: string
  adjudicando?: number | null
  finalizando?: number | null
  errorAdjudicar?: Record<number, string>
  exitoAdjudicar?: Record<number, string>
  errorFinalizar?: Record<number, string>
  exitoFinalizar?: Record<number, string>
  puedeAdjudicar?: boolean
  puedeConfirmar?: boolean
  puedeFinalizar?: boolean
  confirmando?: boolean
  evaluando?: boolean
  confirmada?: boolean
  errorConfirmar?: string | undefined
  exitoConfirmar?: string | undefined
  alAdjudicar?: (ofertaId: number) => void
  alFinalizar?: (ofertaId: number) => void
  alConfirmar?: () => void
}

// Listado de ofertas de una emergencia con las acciones de adjudicación
// (seleccionar, confirmar selección) y de cierre.
// Cada pantalla habilita sólo las acciones que le corresponden a su rol.
export function PanelAdjudicacion({
  ofertas,
  lotes,
  cargando,
  errorCarga,
  titulo = 'Ofertas recibidas',
  mensajeSinOfertas = 'No hay ofertas para esta emergencia.',
  etiquetaVerificada = 'Verificado por Cloud',
  adjudicando = null,
  finalizando = null,
  errorAdjudicar = SIN_MENSAJES,
  exitoAdjudicar = SIN_MENSAJES,
  errorFinalizar = SIN_MENSAJES,
  exitoFinalizar = SIN_MENSAJES,
  puedeAdjudicar = false,
  puedeConfirmar = false,
  puedeFinalizar = false,
  confirmando = false,
  evaluando = false,
  confirmada = false,
  errorConfirmar,
  exitoConfirmar,
  alAdjudicar = sinAccion,
  alFinalizar = sinAccion,
  alConfirmar = sinAccion,
}: PanelAdjudicacionProps) {
  const sinOfertas =
    !cargando && errorCarga === undefined && (ofertas === undefined || ofertas.length === 0)
  const hayAdjudicadas = ofertas?.some(
    (oferta) => oferta.adjudicada_en !== null || exitoAdjudicar[oferta.id] !== undefined,
  ) === true
  const bloqueada = adjudicando !== null || finalizando !== null || confirmando || confirmada || evaluando
  const hayCierrePendiente = ofertas?.some(
    (oferta) => estaAdjudicadaParaCierre(oferta) && !puedeCerrarOferta(oferta, ofertas),
  ) === true

  const lotePorId = new Map(lotes.map((lote) => [lote.id, lote]))

  return (
    <div className={claseSubPanel}>
      <h4 className="text-sm font-bold text-cyan-400">{titulo}</h4>
      <p className="mt-1 text-xs text-slate-400">
        {puedeAdjudicar
          ? 'Selecciona las ofertas evaluadas y confirma la selección para continuar.'
          : 'La oferta adjudicada inicia la atención de la emergencia.'}
      </p>

      {cargando && <p className="mt-3 text-sm text-slate-400">Cargando ofertas...</p>}

      {errorCarga !== undefined && (
        <p role="alert" className={`mt-3 ${claseError}`}>
          No se pudieron cargar las ofertas. {errorCarga}
        </p>
      )}

      {sinOfertas && (
        <p className="mt-3 text-sm text-slate-400">
          {mensajeSinOfertas}
        </p>
      )}

      {puedeFinalizar && !cargando && errorCarga === undefined && hayCierrePendiente && (
        <p role="status" className="mt-3 text-sm text-slate-400">
          Todavía hay ofertas adjudicadas con ítems pendientes de finalización.
        </p>
      )}

      {ofertas !== undefined && ofertas.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {ofertas.map((oferta) => (
            <li
              key={oferta.id}
              className="rounded-xl bg-slate-800 border border-slate-700 p-3 flex flex-col gap-2"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-semibold text-white">
                  {oferta.organizaciones[0]?.nombre ?? `ONG #${oferta.organizacion_id}`}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  Oferta #{oferta.id}
                </span>
              </div>

              <div className="flex flex-wrap gap-2">
                <span className={claseBadge}>
                  {formatearFecha(oferta.fecha_hora_oferta, 'Sin fecha')}
                </span>
                <span className={claseBadge}>Ítems: {oferta.items.length}</span>
              </div>

              <div className="rounded-lg border border-slate-700/80 bg-slate-900/60 p-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Recursos ofrecidos
                </p>
                <ul className="mt-2 flex flex-col gap-2">
                  {oferta.items.map((item) => {
                    const lote = lotePorId.get(item.lote_necesidad_id)
                    const nombreRecurso = item.descripcion ?? lote?.tipo ?? 'Recurso sin nombre'
                    const unidad = lote?.unidad ?? 'unidades'

                    return (
                      <li
                        key={item.id}
                        className="rounded-md border border-slate-700 bg-slate-800/70 px-3 py-2 text-xs"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="font-semibold text-slate-200">{nombreRecurso}</span>
                          <span className="font-mono text-cyan-300">
                            Ofrece: {item.cantidad_ofrecida} {unidad}
                          </span>
                          <span className="font-mono text-cyan-300">
                            {item.cantidad_verificada == null
                              ? 'Pendiente de evaluación'
                              : `${etiquetaVerificada}: ${item.cantidad_verificada}`}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-slate-400">
                          <span>Lote #{item.lote_necesidad_id}</span>
                          {lote !== undefined && (
                            <span>
                              Requerido: {lote.cantidad} {lote.unidad ?? 'unidades'}
                            </span>
                          )}
                          {item.finalizado_en !== null && (
                            <span className="text-emerald-300">
                              Finalizado: {formatearFecha(item.finalizado_en, 'Sin fecha')}
                            </span>
                          )}
                        </div>
                        {lote?.descripcion !== null && lote?.descripcion !== undefined && (
                          <p className="mt-1 text-slate-500">Necesidad: {lote.descripcion}</p>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>

              {(oferta.estado_seleccion === 'adjudicada' ||
                (confirmada && (oferta.adjudicada_en !== null || exitoAdjudicar[oferta.id] !== undefined))) && (
                <p className="rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-300">
                  Oferta adjudicada el {formatearFecha(oferta.adjudicada_en, 'Sin fecha')}
                </p>
              )}

              {!confirmada && (oferta.estado_seleccion === 'seleccionada_para_confirmar' ||
                (oferta.estado_seleccion !== 'adjudicada' && exitoAdjudicar[oferta.id] !== undefined)) && (
                <button type="button" disabled className={`${claseBotonSecundario} self-start text-sm`}>
                  Seleccionada para confirmar
                </button>
              )}

              {puedeAdjudicar && !confirmada && oferta.estado_seleccion === 'sin_seleccionar' &&
                exitoAdjudicar[oferta.id] === undefined && (
                <button
                  type="button"
                  onClick={() => alAdjudicar(oferta.id)}
                  disabled={bloqueada || !oferta.puede_seleccionar || cargando || errorCarga !== undefined}
                  className={`${claseBotonSecundario} self-start text-sm`}
                >
                  {adjudicando === oferta.id ? 'Adjudicando...' : 'Adjudicar'}
                </button>
              )}

              {oferta.estado_seleccion === 'sin_seleccionar' && !oferta.puede_seleccionar &&
                oferta.items.length > 0 && oferta.items.every((item) => (item.cantidad_verificada ?? 0) > 0) && (
                <p className="text-xs text-slate-400">La selección no está habilitada en la etapa actual.</p>
              )}

              {oferta.estado_seleccion === 'adjudicada' && exitoAdjudicar[oferta.id] !== undefined && (
                <p role="status" className={claseExito}>{exitoAdjudicar[oferta.id]}</p>
              )}

              {(() => {
                if (!puedeFinalizar || !puedeCerrarOferta(oferta, ofertas)) {
                  return null
                }

                return (
                  <div className="flex flex-col gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 p-3">
                    {exitoFinalizar[oferta.id] === undefined && (
                      <button
                        type="button"
                        onClick={() => alFinalizar(oferta.id)}
                        disabled={bloqueada || cargando || errorCarga !== undefined}
                        className={`${claseBotonSecundario} self-start text-sm`}
                      >
                        {finalizando === oferta.id ? 'Cerrando oferta...' : 'Cerrar oferta'}
                      </button>
                    )}
                    {exitoFinalizar[oferta.id] !== undefined && (
                      <p role="status" className={claseExito}>{exitoFinalizar[oferta.id]}</p>
                    )}
                    {errorFinalizar[oferta.id] !== undefined && (
                      <p role="alert" className={claseError}>{errorFinalizar[oferta.id]}</p>
                    )}
                  </div>
                )
              })()}

              {errorAdjudicar[oferta.id] !== undefined && (
                <p role="alert" className={claseError}>
                  {errorAdjudicar[oferta.id]}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {puedeConfirmar && ofertas !== undefined && ofertas.length > 0 && (
        <button
          type="button"
          onClick={alConfirmar}
          disabled={bloqueada || !hayAdjudicadas || cargando || errorCarga !== undefined}
          className={`${claseBotonSecundario} mt-3 text-sm`}
        >
          {confirmada ? 'Selección confirmada' : confirmando ? 'Confirmando selección...' : 'Confirmar selección'}
        </button>
      )}
      {errorConfirmar !== undefined && <p role="alert" className={claseError}>{errorConfirmar}</p>}
      {exitoConfirmar !== undefined && <p role="status" className={claseExito}>{exitoConfirmar}</p>}

    </div>
  )
}
