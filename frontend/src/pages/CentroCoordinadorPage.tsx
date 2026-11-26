import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  BORRADOR_VACIO,
  borradorDesdeLote,
  cambiarCampoBorradorLote,
  validarBorradorLote,
} from './formularioLote'
import type { BorradorLote } from './formularioLote'
import {
  ApiError,
  obtenerEmergencia,
  obtenerEvaluacionProyecto,
  evaluarProyecto,
  actualizarLote,
  adjudicarOferta,
  confirmarSeleccionOfertas,
  crearLote,
  eliminarLote,
  finalizarOferta,
  listarBandejaEmergencias,
  sincronizarCierresEmergencias,
  listarOfertasDeEmergencia,
  listarRecursosCloud,
  crearRecursoCloud,
  publicarEmergencia,
} from '../services'
import {
  claseBadge,
  claseBotonSecundario,
  claseExito,
  claseSubPanel,
} from '../ui/clases'
import type {
  AccionEvaluacionProyecto,
  BandaEmergencias,
  EstadoEmergencia,
  EvaluacionProyectoRead,
  EmergenciaRead,
  LoteNecesidad,
  NivelGravedad,
  RecursoCloud,
} from '../types'
import type { OfertaCoordinadorRead } from '../types/oferta'

type PestaniaBandeja = EstadoEmergencia | 'esperando_evaluacion'

const NIVELES_GRAVEDAD: { valor: NivelGravedad; etiqueta: string }[] = [
  { valor: 'baja', etiqueta: 'Baja' },
  { valor: 'media', etiqueta: 'Media' },
  { valor: 'alta', etiqueta: 'Alta' },
  { valor: 'critica', etiqueta: 'Crítica' },
]

const ESTADOS_EMERGENCIA: { valor: EstadoEmergencia; etiqueta: string }[] = [
  { valor: 'esperando_lotes', etiqueta: 'Esperando lotes' },
  { valor: 'esperando_ofertas', etiqueta: 'Esperando ofertas' },
  { valor: 'esperando_adjudicacion', etiqueta: 'Esperando adjudicación' },
  { valor: 'en_proceso', etiqueta: 'En proceso' },
  { valor: 'resuelta', etiqueta: 'Resuelta' },
]

const PESTANIAS_BANDEJA: {
  valor: PestaniaBandeja
  etiqueta: string
  titulo: string
}[] = [
  { valor: 'esperando_lotes', etiqueta: 'Esperando lotes', titulo: 'Emergencias esperando lotes' },
  { valor: 'esperando_ofertas', etiqueta: 'Esperando ofertas', titulo: 'Emergencias esperando ofertas' },
  { valor: 'esperando_evaluacion', etiqueta: 'Esperando Evaluacion', titulo: 'Emergencias esperando evaluación' },
  { valor: 'esperando_adjudicacion', etiqueta: 'Esperando adjudicación', titulo: 'Emergencias esperando adjudicación' },
  { valor: 'en_proceso', etiqueta: 'En proceso', titulo: 'Emergencias en proceso' },
  { valor: 'resuelta', etiqueta: 'Resueltas', titulo: 'Emergencias resueltas' },
]

const DESCRIPCIONES_BANDEJA: Record<PestaniaBandeja, string> = {
  esperando_lotes:
    'Emergencias a la espera de lotes. Tocá una fila para desplegar su detalle, cargar lotes o publicarla.',
  esperando_ofertas:
    'Emergencias publicadas que reciben ofertas de ayuda. Tocá una fila para desplegar su detalle.',
  esperando_adjudicacion:
    'Emergencias listas para seleccionar y adjudicar ofertas.',
  esperando_evaluacion:
    'Emergencias cuya convocatoria terminó y requieren decidir cómo continuar el proyecto.',
  en_proceso: 'Emergencias con ofertas adjudicadas y atención en curso.',
  resuelta: 'Emergencias cuya atención fue resuelta.',
}

interface EstadoEvaluacionProyecto {
  tareaId: number | null
  accion: AccionEvaluacionProyecto | ''
  cargando: boolean
  enviando: boolean
  pendiente: boolean
  requiereConsulta: boolean
  error?: string
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

function normalizarTextoRecurso(texto: string): string {
  return texto.trim().replace(/\s+/g, ' ').toLocaleLowerCase('es-AR')
}

interface EstadoBusquedaRecurso {
  sugerencias: RecursoCloud[]
  cargando: boolean
  error?: string
  creando: boolean
}

const BUSQUEDA_RECURSO_VACIA: EstadoBusquedaRecurso = {
  sugerencias: [],
  cargando: false,
  creando: false,
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

function CamposLote({
  prefijo,
  borrador,
  deshabilitado,
  error,
  alCambiar,
  sugerencias,
  cargandoRecursos,
  errorRecursos,
  creandoRecurso,
  alBuscarRecurso,
  alSeleccionarRecurso,
  alCrearRecurso,
}: {
  prefijo: string
  borrador: BorradorLote
  deshabilitado: boolean
  error: string | undefined
  alCambiar: (campo: keyof BorradorLote, valor: string) => void
  sugerencias: RecursoCloud[]
  cargandoRecursos: boolean
  errorRecursos: string | undefined
  creandoRecurso: boolean
  alBuscarRecurso: (texto: string) => void
  alSeleccionarRecurso: (recurso: RecursoCloud) => void
  alCrearRecurso: () => void
}) {
  const textoRecurso = borrador.tipo.trim()
  const hayCoincidenciaExacta = sugerencias.some(
    (recurso) => normalizarTextoRecurso(recurso.nombre) === normalizarTextoRecurso(textoRecurso),
  )
  const tieneTipoRecursoSeleccionado = Number.isSafeInteger(Number(borrador.tipo_recurso_id)) &&
    Number(borrador.tipo_recurso_id) > 0
  const busquedaSinResultados =
    textoRecurso !== '' &&
    !cargandoRecursos &&
    sugerencias.length === 0 &&
    !hayCoincidenciaExacta &&
    errorRecursos === undefined &&
    !tieneTipoRecursoSeleccionado
  const mostrarBusqueda =
    cargandoRecursos || sugerencias.length > 0 || errorRecursos !== undefined || busquedaSinResultados

  return (
    <>
      <div>
        <label htmlFor={`${prefijo}-tipo`} className={claseEtiqueta}>
          Tipo
        </label>
        <input
          id={`${prefijo}-tipo`}
          disabled={deshabilitado}
          type="text"
          value={borrador.tipo}
          onChange={(evento) => {
            alCambiar('tipo', evento.target.value)
            alBuscarRecurso(evento.target.value)
          }}
          onKeyDown={(evento) => {
            if (evento.key === 'Enter' && sugerencias[0] !== undefined) {
              evento.preventDefault()
              alSeleccionarRecurso(sugerencias[0])
            }
          }}
          placeholder="Colchones"
          maxLength={120}
          required
          className={claseCampo}
        />
        {mostrarBusqueda && (
          <div className="relative z-10">
            <div
              role="listbox"
              className="absolute mt-1 max-h-48 w-full overflow-auto rounded-lg border border-slate-700 bg-slate-800 shadow-xl"
            >
              {cargandoRecursos && (
                <p className="px-3 py-2 text-xs text-slate-400">Buscando recursos...</p>
              )}
              {!cargandoRecursos && sugerencias.map((recurso) => (
                <button
                  key={recurso.id}
                  type="button"
                  role="option"
                  onClick={() => alSeleccionarRecurso(recurso)}
                  className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-700"
                >
                  <span className="font-semibold">{recurso.nombre}</span>
                  {recurso.descripcion && (
                    <span className="ml-2 text-xs text-slate-400">{recurso.descripcion}</span>
                  )}
                </button>
              ))}
              {busquedaSinResultados && (
                <button
                  type="button"
                  onClick={alCrearRecurso}
                  disabled={deshabilitado || creandoRecurso}
                  className="block w-full border-t border-slate-700 px-3 py-2 text-left text-sm font-semibold text-cyan-400 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creandoRecurso ? 'Creando recurso...' : `Crear recurso «${textoRecurso}»`}
                </button>
              )}
              {errorRecursos !== undefined && (
                <p role="alert" className="border-t border-red-500/30 px-3 py-2 text-xs text-red-300">
                  {errorRecursos}
                </p>
              )}
            </div>
          </div>
        )}
        <p className="mt-1 text-xs text-slate-400">
          Buscá un recurso nacional o crealo si todavía no existe.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="flex-1 min-w-32">
          <label htmlFor={`${prefijo}-cantidad`} className={claseEtiqueta}>
            Cantidad
          </label>
          <input
            id={`${prefijo}-cantidad`}
            disabled={deshabilitado}
            type="number"
            min={1}
            step={1}
            value={borrador.cantidad}
            onChange={(evento) => alCambiar('cantidad', evento.target.value)}
            placeholder="50"
            required
            className={claseCampo}
          />
        </div>

        <div className="flex-1 min-w-32">
          <label htmlFor={`${prefijo}-unidad`} className={claseEtiqueta}>
            Unidad de medida (opcional)
          </label>
          <input
            id={`${prefijo}-unidad`}
            disabled={deshabilitado}
            type="text"
            value={borrador.unidad}
            onChange={(evento) => alCambiar('unidad', evento.target.value)}
            placeholder="kg, litros, cajas, bolsas"
            maxLength={50}
            className={claseCampo}
          />
        </div>
      </div>

      <div>
        <label htmlFor={`${prefijo}-descripcion`} className={claseEtiqueta}>
          Descripción (opcional)
        </label>
        <textarea
          id={`${prefijo}-descripcion`}
          disabled={deshabilitado}
          value={borrador.descripcion}
          onChange={(evento) => alCambiar('descripcion', evento.target.value)}
          placeholder="Detalle del lote, dónde se entrega, prioridad."
          rows={2}
          className={claseCampo}
        />
      </div>

      {error !== undefined && (
        <p role="alert" className={claseError}>
          {error}
        </p>
      )}
    </>
  )
}

function BotonEnviarLote({
  guardando,
  texto,
  textoGuardando,
}: {
  guardando: boolean
  texto: string
  textoGuardando: string
}) {
  return (
    <button
      type="submit"
      disabled={guardando}
      className="rounded-lg bg-cyan-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {guardando ? textoGuardando : texto}
    </button>
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
  busquedaRecursoEdicion,
  alBuscarRecursoEdicion,
  alSeleccionarRecursoEdicion,
  alCrearRecursoEdicion,
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
  busquedaRecursoEdicion: EstadoBusquedaRecurso
  alBuscarRecursoEdicion: (texto: string) => void
  alSeleccionarRecursoEdicion: (recurso: RecursoCloud) => void
  alCrearRecursoEdicion: () => void
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

                <CamposLote
                  prefijo={`lote-edicion-${lote.id}`}
                  borrador={borradorEdicion}
                  deshabilitado={guardandoEdicion}
                  error={errorEdicion}
                  alCambiar={alCambiarCampoEdicion}
                  sugerencias={busquedaRecursoEdicion.sugerencias}
                  cargandoRecursos={busquedaRecursoEdicion.cargando}
                  errorRecursos={busquedaRecursoEdicion.error}
                  creandoRecurso={busquedaRecursoEdicion.creando}
                  alBuscarRecurso={alBuscarRecursoEdicion}
                  alSeleccionarRecurso={alSeleccionarRecursoEdicion}
                  alCrearRecurso={alCrearRecursoEdicion}
                />

                <div className="flex flex-wrap gap-2">
                  <BotonEnviarLote
                    guardando={guardandoEdicion}
                    texto="Guardar"
                    textoGuardando="Guardando..."
                  />
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
                    disabled={eliminandoLote !== null || guardandoEdicion}
                    className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    onClick={() => alEliminar(lote)}
                    disabled={eliminandoLote !== null || guardandoEdicion}
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

function PanelAdjudicacion({
  ofertas,
  lotes,
  cargando,
  errorCarga,
  adjudicando,
  finalizando,
  errorAdjudicar,
  exitoAdjudicar,
  errorFinalizar,
  exitoFinalizar,
  puedeAdjudicar,
  puedeConfirmar,
  confirmando,
  evaluando,
  confirmada,
  errorConfirmar,
  exitoConfirmar,
  alAdjudicar,
  alFinalizar,
  alConfirmar,
}: {
  ofertas: OfertaCoordinadorRead[] | undefined
  lotes: LoteNecesidad[]
  cargando: boolean
  errorCarga: string | undefined
  adjudicando: number | null
  finalizando: number | null
  errorAdjudicar: Record<number, string>
  exitoAdjudicar: Record<number, string>
  errorFinalizar: Record<number, string>
  exitoFinalizar: Record<number, string>
  puedeAdjudicar: boolean
  puedeConfirmar: boolean
  confirmando: boolean
  evaluando: boolean
  confirmada: boolean
  errorConfirmar: string | undefined
  exitoConfirmar: string | undefined
  alAdjudicar: (ofertaId: number, paraSeleccion: boolean) => void
  alFinalizar: (ofertaId: number) => void
  alConfirmar: () => void
}) {
  const sinOfertas =
    !cargando && errorCarga === undefined && (ofertas === undefined || ofertas.length === 0)
  const hayAdjudicadas = ofertas?.some(
    (oferta) => oferta.adjudicada_en !== null || exitoAdjudicar[oferta.id] !== undefined,
  ) === true
  const bloqueada = adjudicando !== null || finalizando !== null || confirmando || confirmada || evaluando

  const lotePorId = new Map(lotes.map((lote) => [lote.id, lote]))

  return (
    <div className={claseSubPanel}>
      <h4 className="text-sm font-bold text-cyan-400">Ofertas recibidas</h4>
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
          No hay ofertas para esta emergencia.
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
                              : `Verificado por Cloud: ${item.cantidad_verificada}`}
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
                  onClick={() => alAdjudicar(oferta.id, true)}
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

              {puedeAdjudicar && !confirmada && !hayAdjudicadas && oferta.adjudicada_en === null && (
                <button
                  type="button"
                  onClick={() => {
                    const confirmado = window.confirm(
                      `¿Adjudicar la oferta #${oferta.id}? Se adjudicará esta oferta y no podrás elegir otra.`,
                    )
                    if (confirmado) {
                      alAdjudicar(oferta.id, false)
                    }
                  }}
                  disabled={bloqueada || cargando || errorCarga !== undefined}
                  className={`${claseBotonSecundario} self-start text-sm`}
                >
                  Adjudicar solo esta oferta
                </button>
              )}

              {oferta.estado_seleccion === 'adjudicada' && exitoAdjudicar[oferta.id] !== undefined && (
                <p role="status" className={claseExito}>{exitoAdjudicar[oferta.id]}</p>
              )}

              {(() => {
                const estaAdjudicada = oferta.estado_seleccion === 'adjudicada' ||
                  oferta.adjudicada_en !== null || exitoAdjudicar[oferta.id] !== undefined
                const itemsFinalizados = oferta.items.length > 0 &&
                  oferta.items.every((item) => item.finalizado_en !== null)

                if (!estaAdjudicada || !itemsFinalizados) {
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

export function CentroCoordinadorPage() {
  const [pestania, setPestania] = useState<PestaniaBandeja>('esperando_lotes')
  const pestaniaActual = useRef<PestaniaBandeja>('esperando_lotes')
  const versionPestania = useRef(0)
  const montada = useRef(true)
  const [pagina, setPagina] = useState(1)
  const [bandeja, setBandeja] = useState<BandaEmergencias | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [avisoSincronizacion, setAvisoSincronizacion] = useState<string | null>(null)
  const [exitoCierre, setExitoCierre] = useState<string | null>(null)
  const [recargo, setRecargo] = useState(0)
  const [desplegadas, setDesplegadas] = useState<Set<number>>(() => new Set())
  const [borradores, setBorradores] = useState<Record<number, BorradorLote>>({})
  const [errorBorrador, setErrorBorrador] = useState<Record<number, string>>({})
  const [busquedasRecursos, setBusquedasRecursos] = useState<
    Record<number, EstadoBusquedaRecurso>
  >({})
  const [enviandoLote, setEnviandoLote] = useState<Record<number, boolean>>({})
  const [publicando, setPublicando] = useState<Record<number, boolean>>({})
  const [errorPublicar, setErrorPublicar] = useState<Record<number, string>>({})
  const [loteEnEdicion, setLoteEnEdicion] = useState<number | null>(null)
  const [borradorEdicion, setBorradorEdicion] = useState<BorradorLote>(BORRADOR_VACIO)
  const [errorEdicion, setErrorEdicion] = useState<string | undefined>(undefined)
  const [busquedaRecursoEdicion, setBusquedaRecursoEdicion] =
    useState<EstadoBusquedaRecurso>(BUSQUEDA_RECURSO_VACIA)
  const [guardandoEdicion, setGuardandoEdicion] = useState(false)
  const [eliminandoLote, setEliminandoLote] = useState<number | null>(null)
  const [avisoLote, setAvisoLote] = useState<string | null>(null)
  const [ofertasPorEmergencia, setOfertasPorEmergencia] = useState<
    Record<number, OfertaCoordinadorRead[]>
  >({})
  const [cargandoOfertas, setCargandoOfertas] = useState<Record<number, boolean>>({})
  const [errorOfertas, setErrorOfertas] = useState<Record<number, string>>({})
  const [adjudicando, setAdjudicando] = useState<Record<number, number>>({})
  const [finalizando, setFinalizando] = useState<Record<number, number>>({})
  const [errorAdjudicar, setErrorAdjudicar] = useState<Record<number, string>>({})
  const [exitoAdjudicar, setExitoAdjudicar] = useState<Record<number, string>>({})
  const [errorFinalizar, setErrorFinalizar] = useState<Record<number, string>>({})
  const [exitoFinalizar, setExitoFinalizar] = useState<Record<number, string>>({})
  const [confirmando, setConfirmando] = useState<Record<number, boolean>>({})
  const [confirmadas, setConfirmadas] = useState<Record<number, boolean>>({})
  const [errorConfirmar, setErrorConfirmar] = useState<Record<number, string>>({})
  const [exitoConfirmar, setExitoConfirmar] = useState<Record<number, string>>({})
  const [evaluacionesProyecto, setEvaluacionesProyecto] = useState<Record<number, EstadoEvaluacionProyecto>>({})
  const evaluacionesVigentes = useRef<Record<number, EstadoEvaluacionProyecto>>({})
  const versionesEvaluacion = useRef<Record<number, number>>({})
  const operacionesOfertas = useRef(new Set<number>())
  const adjudicadasRecientes = useRef(new Set<number>())
  const confirmadasRecientes = useRef(new Set<number>())
  const ofertasVigentes = useRef<Record<number, OfertaCoordinadorRead[]>>({})
  const revisionLotes = useRef(0)
  const versionesBusquedaRecursos = useRef<Record<number, number>>({})
  const versionBusquedaEdicion = useRef(0)

  const actualizarEvaluacionProyecto = useCallback((emergenciaId: number, cambios: Partial<EstadoEvaluacionProyecto>) => {
    const estado: EstadoEvaluacionProyecto = {
      ...(evaluacionesVigentes.current[emergenciaId] ?? {
        tareaId: null, accion: '', cargando: false, enviando: false, pendiente: false, requiereConsulta: false,
      }),
      ...cambios,
    }
    evaluacionesVigentes.current[emergenciaId] = estado
    setEvaluacionesProyecto((actuales) => ({ ...actuales, [emergenciaId]: estado }))
  }, [])

  useEffect(() => {
    montada.current = true
    return () => { montada.current = false }
  }, [])

  useEffect(() => {
    let vigente = true
    const version = versionPestania.current
    const sigueVigente = () => vigente && pestaniaActual.current === pestania && versionPestania.current === version

    async function cargar() {
      const revision = revisionLotes.current
      setCargando(true)
      setError(null)
      setAvisoSincronizacion(null)
      try {
        if (pestania === 'en_proceso' || pestania === 'resuelta') {
          try {
            await sincronizarCierresEmergencias()
          } catch {
            if (sigueVigente()) {
              setAvisoSincronizacion('No se pudieron actualizar los cierres. Recargá la bandeja para volver a intentarlo.')
            }
          }
          if (!sigueVigente()) return
        }
        const datos = await listarBandejaEmergencias({
          publicada: pestania !== 'esperando_lotes',
          ...(pestania === 'esperando_ofertas' || pestania === 'esperando_evaluacion' || pestania === 'esperando_adjudicacion'
            ? { etapa_bonita: pestania }
            : { estado: pestania }),
          pagina,
          por_pagina: POR_PAGINA,
        })
        if (!sigueVigente()) {
          return
        }
        if (revision !== revisionLotes.current) {
          // La lectura empezó antes de un cambio confirmado: pedimos datos actuales.
          setRecargo((actual) => actual + 1)
          return
        }
        setBandeja(datos)
        if (pestania === 'esperando_adjudicacion') {
          for (const emergencia of datos.items) {
            if (evaluacionesVigentes.current[emergencia.id] !== undefined &&
              !operacionesOfertas.current.has(emergencia.id)) {
              // La bandeja vigente confirma la tarea de selección de este caso.
              versionesEvaluacion.current[emergencia.id] = (versionesEvaluacion.current[emergencia.id] ?? 0) + 1
              actualizarEvaluacionProyecto(emergencia.id, {
                tareaId: null, accion: '', pendiente: false, cargando: false, requiereConsulta: false, error: undefined,
              })
            }
          }
        }
        if (datos.paginas > 0 && datos.pagina > datos.paginas) {
          setPagina(datos.paginas)
        }
      } catch (fallo) {
        if (sigueVigente()) {
          setError(describirError(fallo))
        }
      } finally {
        if (sigueVigente()) {
          setCargando(false)
        }
      }
    }

    void cargar()

    return () => {
      vigente = false
    }
  }, [pestania, pagina, recargo, actualizarEvaluacionProyecto])

  const cargarEvaluacionProyecto = useCallback(async (emergenciaId: number, incluirSeleccion = false): Promise<EvaluacionProyectoRead | undefined> => {
    if (operacionesOfertas.current.has(emergenciaId)) return
    const version = (versionesEvaluacion.current[emergenciaId] ?? 0) + 1
    versionesEvaluacion.current[emergenciaId] = version
    actualizarEvaluacionProyecto(emergenciaId, { cargando: true })
    try {
      const respuesta = await obtenerEvaluacionProyecto(emergenciaId, incluirSeleccion)
      if (versionesEvaluacion.current[emergenciaId] !== version) return
      const cambioTarea = evaluacionesVigentes.current[emergenciaId]?.tareaId !== respuesta.tarea_id
      actualizarEvaluacionProyecto(emergenciaId, {
        tareaId: respuesta.tarea_id, requiereConsulta: false, error: undefined,
        ...(cambioTarea ? { accion: '' as const } : {}),
      })
      return respuesta
    } catch (fallo) {
      if (versionesEvaluacion.current[emergenciaId] !== version) return
      actualizarEvaluacionProyecto(emergenciaId, { requiereConsulta: true, error: describirError(fallo) })
    } finally {
      if (versionesEvaluacion.current[emergenciaId] === version) actualizarEvaluacionProyecto(emergenciaId, { cargando: false })
    }
  }, [actualizarEvaluacionProyecto])

  useEffect(() => {
    if (pestania !== 'esperando_evaluacion') return
    for (const emergencia of bandeja?.items ?? []) {
      if (desplegadas.has(emergencia.id)) void cargarEvaluacionProyecto(emergencia.id)
    }
  }, [bandeja, desplegadas, pestania, cargarEvaluacionProyecto])

  function evaluacionBloquea(emergenciaId: number): boolean {
    const evaluacion = evaluacionesVigentes.current[emergenciaId]
    return evaluacion !== undefined && (evaluacion.cargando || evaluacion.enviando || evaluacion.pendiente ||
      evaluacion.tareaId !== null)
  }

  async function actualizarEstadoProyecto(emergenciaId: number): Promise<void> {
    if (operacionesOfertas.current.has(emergenciaId) || evaluacionesVigentes.current[emergenciaId]?.cargando) return
    actualizarEvaluacionProyecto(emergenciaId, { cargando: true })
    try {
      const emergencia = await obtenerEmergencia(emergenciaId)
      const evaluacion = await cargarEvaluacionProyecto(emergenciaId, true)
      if (evaluacion?.tarea_id === null && (evaluacion.seleccion_oferta_lista === true ||
        emergencia.estado === 'esperando_ofertas' || emergencia.estado === 'esperando_lotes')) {
        actualizarEvaluacionProyecto(emergenciaId, { pendiente: false })
        if (evaluacion.seleccion_oferta_lista === true) {
          await cargarOfertasDeEmergencia(emergenciaId)
          cambiarPestania('esperando_adjudicacion')
        } else if (emergencia.estado !== null) {
          cambiarPestania(emergencia.estado)
        }
        setRecargo((actual) => actual + 1)
      }
    } catch (fallo) {
      actualizarEvaluacionProyecto(emergenciaId, { requiereConsulta: true, error: describirError(fallo) })
    } finally {
      actualizarEvaluacionProyecto(emergenciaId, { cargando: false })
    }
  }

  async function manejarEvaluarProyecto(emergenciaId: number, tareaId: number): Promise<void> {
    const evaluacion = evaluacionesVigentes.current[emergenciaId]
    if (pestaniaActual.current !== 'esperando_evaluacion' || operacionesOfertas.current.has(emergenciaId) ||
      evaluacion?.tareaId !== tareaId || evaluacion.cargando || evaluacion.enviando ||
      evaluacion.pendiente || evaluacion.requiereConsulta || evaluacion.accion === '') return
    operacionesOfertas.current.add(emergenciaId)
    versionesEvaluacion.current[emergenciaId] = (versionesEvaluacion.current[emergenciaId] ?? 0) + 1
    actualizarEvaluacionProyecto(emergenciaId, { enviando: true, error: undefined })
    let aceptada = false
    try {
      const respuesta = await evaluarProyecto(emergenciaId, { tarea_id: tareaId, accion: evaluacion.accion })
      if (respuesta.tarea_id !== tareaId) throw new ApiError(202, 'La respuesta de evaluación no pudo verificarse.')
      aceptada = true
      actualizarEvaluacionProyecto(emergenciaId, { tareaId: null, pendiente: true })
    } catch (fallo) {
      actualizarEvaluacionProyecto(emergenciaId, { requiereConsulta: true, error: describirError(fallo) })
    } finally {
      operacionesOfertas.current.delete(emergenciaId)
      actualizarEvaluacionProyecto(emergenciaId, { enviando: false })
    }
    if (aceptada) await actualizarEstadoProyecto(emergenciaId)
  }

  function cambiarPestania(valor: PestaniaBandeja) {
    if (pestaniaActual.current !== valor) versionPestania.current += 1
    pestaniaActual.current = valor
    setAvisoSincronizacion(null)
    setExitoCierre(null)
    setPagina(1)
    setPestania(valor)
    if (valor === 'esperando_ofertas' || valor === 'esperando_adjudicacion' || valor === 'en_proceso') {
      for (const emergenciaId of desplegadas) {
        if (ofertasVigentes.current[emergenciaId] === undefined) void cargarOfertasDeEmergencia(emergenciaId)
      }
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
      setErrorOfertas((actuales) => ({
        ...actuales,
        [emergenciaId]: describirError(fallo),
      }))
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
      operacionesOfertas.current.has(emergenciaId) || evaluacionBloquea(emergenciaId) ||
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
      setExitoAdjudicar((actuales) => ({
        ...actuales,
        [ofertaId]: respuesta.mensaje,
      }))
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
      setErrorAdjudicar((actuales) => ({
        ...actuales,
        [ofertaId]: describirError(fallo),
      }))
    } finally {
      operacionesOfertas.current.delete(emergenciaId)
      setAdjudicando((actuales) => sinClave(actuales, emergenciaId))
    }
  }

  async function manejarConfirmarSeleccion(emergenciaId: number): Promise<void> {
    const ofertas = ofertasVigentes.current[emergenciaId]
    if (
      (pestaniaActual.current !== 'esperando_adjudicacion' && pestaniaActual.current !== 'en_proceso') ||
      operacionesOfertas.current.has(emergenciaId) || evaluacionBloquea(emergenciaId) || confirmadasRecientes.current.has(emergenciaId) ||
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

  async function manejarFinalizarOferta(emergenciaId: number, ofertaId: number): Promise<void> {
    const oferta = ofertasVigentes.current[emergenciaId]?.find((registro) => registro.id === ofertaId)
    if (
      pestaniaActual.current !== 'en_proceso' || oferta === undefined ||
      operacionesOfertas.current.has(emergenciaId) ||
      (oferta.estado_seleccion !== 'adjudicada' && oferta.adjudicada_en === null) ||
      oferta.items.length === 0 ||
      !oferta.items.every((item) => item.finalizado_en !== null)
    ) return

    const version = versionPestania.current
    const sigueVigente = () => montada.current && pestaniaActual.current === 'en_proceso' && versionPestania.current === version
    operacionesOfertas.current.add(emergenciaId)
    setFinalizando((actuales) => ({ ...actuales, [emergenciaId]: ofertaId }))
    setErrorFinalizar((actuales) => sinClave(actuales, ofertaId))
    setExitoFinalizar((actuales) => sinClave(actuales, ofertaId))
    try {
      const respuesta = await finalizarOferta(ofertaId)
      if (
        respuesta?.oferta_id !== ofertaId ||
        respuesta.estado !== 'finalizada' ||
        typeof respuesta.mensaje !== 'string'
      ) {
        throw new ApiError(200, 'La respuesta de cierre de oferta no pudo verificarse.')
      }
      if (!sigueVigente()) return
      setExitoFinalizar((actuales) => ({
        ...actuales,
        [ofertaId]: 'Se registró el cierre de la oferta.',
      }))
      await cargarOfertasDeEmergencia(emergenciaId)
      if (!sigueVigente()) return
      try {
        const sincronizacion = await sincronizarCierresEmergencias()
        if (!sigueVigente()) return
        let resuelta = sincronizacion.emergencias_resueltas.includes(emergenciaId)
        if (!resuelta) {
          const emergencia = await obtenerEmergencia(emergenciaId)
          resuelta = emergencia.id === emergenciaId && emergencia.estado === 'resuelta'
        }
        if (!sigueVigente()) return
        if (resuelta) {
          cambiarPestania('resuelta')
          setExitoCierre('La emergencia se cerró y está en Resueltas.')
        }
      } catch {
        if (sigueVigente()) {
          setAvisoSincronizacion('Se registró el cierre de la oferta, pero no se pudo actualizar su estado. Recargá la bandeja para volver a intentarlo.')
        }
      }
    } catch {
      if (sigueVigente()) {
        setErrorFinalizar((actuales) => ({ ...actuales, [ofertaId]: 'No se pudo cerrar la oferta. Intentá de nuevo.' }))
      }
    } finally {
      operacionesOfertas.current.delete(emergenciaId)
      if (montada.current) setFinalizando((actuales) => sinClave(actuales, emergenciaId))
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

    // Las ofertas se piden una sola vez por emergencia, en los estados donde
    // corresponde revisarlas o adjudicarlas.
    if (
      desplegando &&
      (pestania === 'esperando_ofertas' || pestania === 'esperando_adjudicacion' || pestania === 'en_proceso') &&
      ofertasPorEmergencia[emergenciaId] === undefined
    ) {
      void cargarOfertasDeEmergencia(emergenciaId)
    }
  }

  function actualizarBorrador(
    emergenciaId: number,
    campo: keyof BorradorLote,
    valor: string,
  ) {
    setBorradores((actuales) => {
      const actual = actuales[emergenciaId] ?? BORRADOR_VACIO
      return {
        ...actuales,
        [emergenciaId]: cambiarCampoBorradorLote(actual, campo, valor),
      }
    })
    setErrorBorrador((actuales) => sinClave(actuales, emergenciaId))
  }

  async function buscarRecursosParaNuevoLote(emergenciaId: number, texto: string) {
    const version = (versionesBusquedaRecursos.current[emergenciaId] ?? 0) + 1
    versionesBusquedaRecursos.current[emergenciaId] = version
    if (!texto.trim()) {
      setBusquedasRecursos((actuales) => ({
        ...actuales,
        [emergenciaId]: BUSQUEDA_RECURSO_VACIA,
      }))
      return
    }
    setBusquedasRecursos((actuales) => ({
      ...actuales,
      [emergenciaId]: { ...(actuales[emergenciaId] ?? BUSQUEDA_RECURSO_VACIA), cargando: true, error: undefined },
    }))
    try {
      const sugerencias = await listarRecursosCloud(texto)
      if (versionesBusquedaRecursos.current[emergenciaId] !== version) {
        return
      }
      setBusquedasRecursos((actuales) => ({
        ...actuales,
        [emergenciaId]: { sugerencias, cargando: false, creando: false },
      }))
    } catch (fallo) {
      if (versionesBusquedaRecursos.current[emergenciaId] !== version) {
        return
      }
      setBusquedasRecursos((actuales) => ({
        ...actuales,
        [emergenciaId]: {
          ...(actuales[emergenciaId] ?? BUSQUEDA_RECURSO_VACIA),
          cargando: false,
          error: describirError(fallo),
        },
      }))
    }
  }

  function seleccionarRecursoNuevo(emergenciaId: number, recurso: RecursoCloud) {
    versionesBusquedaRecursos.current[emergenciaId] =
      (versionesBusquedaRecursos.current[emergenciaId] ?? 0) + 1
    actualizarBorrador(emergenciaId, 'tipo', recurso.nombre)
    setBorradores((actuales) => ({
      ...actuales,
      [emergenciaId]: {
        ...(actuales[emergenciaId] ?? BORRADOR_VACIO),
        tipo: recurso.nombre,
        tipo_recurso_id: String(recurso.id),
      },
    }))
    setBusquedasRecursos((actuales) => ({
      ...actuales,
      [emergenciaId]: BUSQUEDA_RECURSO_VACIA,
    }))
  }

  async function crearRecursoParaNuevoLote(emergenciaId: number) {
    const borrador = borradores[emergenciaId] ?? BORRADOR_VACIO
    const nombre = borrador.tipo.trim()
    if (!nombre) return
    setBusquedasRecursos((actuales) => ({
      ...actuales,
      [emergenciaId]: { ...(actuales[emergenciaId] ?? BUSQUEDA_RECURSO_VACIA), creando: true, error: undefined },
    }))
    try {
      const recurso = await crearRecursoCloud({ nombre, descripcion: borrador.descripcion.trim() || null })
      seleccionarRecursoNuevo(emergenciaId, recurso)
    } catch (fallo) {
      setBusquedasRecursos((actuales) => ({
        ...actuales,
        [emergenciaId]: { ...(actuales[emergenciaId] ?? BUSQUEDA_RECURSO_VACIA), creando: false, error: describirError(fallo) },
      }))
    }
  }

  function actualizarLotesEnBandeja(
    emergenciaId: number,
    transformar: (emergencia: EmergenciaRead) => EmergenciaRead,
  ) {
    revisionLotes.current += 1
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

    const validacion = validarBorradorLote(borradores[emergencia.id] ?? BORRADOR_VACIO)

    if (validacion.error !== null) {
      setErrorBorrador((actuales) => ({
        ...actuales,
        [emergencia.id]: validacion.error,
      }))
      return
    }

    setEnviandoLote((actuales) => ({ ...actuales, [emergencia.id]: true }))
    try {
      const creado = await crearLote(emergencia.id, validacion.datos)
      actualizarLotesEnBandeja(emergencia.id, (item) => ({
        ...item,
        lotes: item.lotes.some((lote) => lote.id === creado.id)
          ? item.lotes
          : [...item.lotes, creado],
      }))
      setErrorBorrador((actuales) => sinClave(actuales, emergencia.id))
      setBorradores((actuales) => sinClave(actuales, emergencia.id))
    } catch (fallo) {
      setErrorBorrador((actuales) => ({
        ...actuales,
        [emergencia.id]: describirError(fallo),
      }))
    } finally {
      setEnviandoLote((actuales) => sinClave(actuales, emergencia.id))
    }
  }

  function abrirEdicionLote(lote: LoteNecesidad) {
    setLoteEnEdicion(lote.id)
    setBorradorEdicion(borradorDesdeLote(lote))
    setErrorEdicion(undefined)
    setAvisoLote(null)
    setBusquedaRecursoEdicion(BUSQUEDA_RECURSO_VACIA)
  }

  function cerrarEdicionLote() {
    setLoteEnEdicion(null)
    setBorradorEdicion(BORRADOR_VACIO)
    setErrorEdicion(undefined)
  }

  function cambiarCampoEdicion(campo: keyof BorradorLote, valor: string) {
    setBorradorEdicion((actual) => cambiarCampoBorradorLote(actual, campo, valor))
    setErrorEdicion(undefined)
  }

  async function buscarRecursoEdicion(texto: string) {
    const version = versionBusquedaEdicion.current + 1
    versionBusquedaEdicion.current = version
    if (!texto.trim()) {
      setBusquedaRecursoEdicion(BUSQUEDA_RECURSO_VACIA)
      return
    }
    setBusquedaRecursoEdicion((actual) => ({ ...actual, cargando: true, error: undefined }))
    try {
      const sugerencias = await listarRecursosCloud(texto)
      if (versionBusquedaEdicion.current !== version) {
        return
      }
      setBusquedaRecursoEdicion({ sugerencias, cargando: false, creando: false })
    } catch (fallo) {
      if (versionBusquedaEdicion.current !== version) {
        return
      }
      setBusquedaRecursoEdicion((actual) => ({ ...actual, cargando: false, error: describirError(fallo) }))
    }
  }

  function seleccionarRecursoEdicion(recurso: RecursoCloud) {
    versionBusquedaEdicion.current += 1
    setBorradorEdicion((actual) => ({
      ...actual,
      tipo: recurso.nombre,
      tipo_recurso_id: String(recurso.id),
    }))
    setBusquedaRecursoEdicion(BUSQUEDA_RECURSO_VACIA)
  }

  async function crearRecursoEdicion() {
    const nombre = borradorEdicion.tipo.trim()
    if (!nombre) return
    setBusquedaRecursoEdicion((actual) => ({ ...actual, creando: true, error: undefined }))
    try {
      const recurso = await crearRecursoCloud({
        nombre,
        descripcion: borradorEdicion.descripcion.trim() || null,
      })
      seleccionarRecursoEdicion(recurso)
    } catch (fallo) {
      setBusquedaRecursoEdicion((actual) => ({ ...actual, creando: false, error: describirError(fallo) }))
    }
  }

  async function manejarEnvioEdicion(
    evento: FormEvent<HTMLFormElement>,
    lote: LoteNecesidad,
  ) {
    evento.preventDefault()

    const validacion = validarBorradorLote(borradorEdicion)

    if (validacion.error !== null) {
      setErrorEdicion(validacion.error)
      return
    }

    setGuardandoEdicion(true)
    try {
      const actualizado = await actualizarLote(lote.id, validacion.datos)
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
    setPublicando((actuales) => ({ ...actuales, [emergencia.id]: true }))
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
      setPublicando((actuales) => sinClave(actuales, emergencia.id))
    }
  }

  const totalPaginas = bandeja?.paginas ?? 0
  const paginaActual = bandeja?.pagina ?? pagina
  const sinPaginas = totalPaginas === 0
  const editable = pestania === 'esperando_lotes'
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

      {exitoCierre !== null && <p role="status" className={claseExito}>{exitoCierre}</p>}
      {avisoSincronizacion !== null && <p role="alert" className={claseError}>{avisoSincronizacion}</p>}

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
          No hay emergencias en este estado.
        </p>
      )}

      {!cargando && error === null && bandeja !== null && bandeja.items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {bandeja.items.map((emergencia) => {
            const desplegada = desplegadas.has(emergencia.id)
            const borrador = borradores[emergencia.id] ?? BORRADOR_VACIO
            const errorFormulario = errorBorrador[emergencia.id]
            const errorPublicacion = errorPublicar[emergencia.id]
            const guardandoLote = enviandoLote[emergencia.id] ?? false

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
                      Estado: {pestania === 'esperando_evaluacion' ? 'Esperando Evaluacion' : etiquetaDeEstado(emergencia.estado)}
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
                      busquedaRecursoEdicion={busquedaRecursoEdicion}
                      alBuscarRecursoEdicion={(texto) => void buscarRecursoEdicion(texto)}
                      alSeleccionarRecursoEdicion={seleccionarRecursoEdicion}
                      alCrearRecursoEdicion={() => void crearRecursoEdicion()}
                      alEnviarEdicion={(evento, lote) =>
                        void manejarEnvioEdicion(evento, lote)
                      }
                      alEliminar={(lote) => void manejarEliminar(lote)}
                    />

                    {pestania === 'esperando_evaluacion' && (
                      <div className={claseSubPanel}>
                        {evaluacionesProyecto[emergencia.id]?.tareaId != null && !evaluacionesProyecto[emergencia.id]?.pendiente && (
                          <>
                            <h4 className="text-sm font-bold text-cyan-400">Evaluar proyecto</h4>
                            <label htmlFor={`evaluacion-proyecto-${emergencia.id}`} className={claseEtiqueta}>Decisión</label>
                            <select
                              id={`evaluacion-proyecto-${emergencia.id}`}
                              value={evaluacionesProyecto[emergencia.id].accion}
                              disabled={evaluacionesProyecto[emergencia.id].cargando || evaluacionesProyecto[emergencia.id].enviando || evaluacionesProyecto[emergencia.id].requiereConsulta}
                              onChange={(evento) => actualizarEvaluacionProyecto(emergencia.id, { accion: evento.target.value as AccionEvaluacionProyecto })}
                              className={claseCampo}
                            >
                              <option value="" disabled>Elegir una decisión</option>
                              <option value="REABRIR">Reabrir convocatoria</option>
                              <option value="REFORMULAR">Reformular pedido</option>
                              <option value="CONTINUAR_PARCIAL">Continuar con cobertura parcial</option>
                            </select>
                            <button
                              type="button"
                              disabled={evaluacionesProyecto[emergencia.id].cargando || evaluacionesProyecto[emergencia.id].enviando || evaluacionesProyecto[emergencia.id].requiereConsulta || evaluacionesProyecto[emergencia.id].accion === ''}
                              onClick={() => void manejarEvaluarProyecto(emergencia.id, evaluacionesProyecto[emergencia.id].tareaId!)}
                              className={`${claseBotonSecundario} mt-3 text-sm`}
                            >
                              {evaluacionesProyecto[emergencia.id].enviando ? 'Enviando decisión...' : 'Confirmar decisión'}
                            </button>
                          </>
                        )}
                        {evaluacionesProyecto[emergencia.id]?.error && <p role="alert" className={claseError}>{evaluacionesProyecto[emergencia.id].error}</p>}
                        {evaluacionesProyecto[emergencia.id]?.pendiente && <p role="status" className="text-sm text-slate-300">Decisión enviada. Esperando el siguiente paso del proceso.</p>}
                        {evaluacionesProyecto[emergencia.id]?.cargando && <p className="text-sm text-slate-400">Consultando etapa del proyecto...</p>}
                        <button
                          type="button"
                          disabled={evaluacionesProyecto[emergencia.id]?.cargando || evaluacionesProyecto[emergencia.id]?.enviando}
                          onClick={() => void actualizarEstadoProyecto(emergencia.id)}
                          className={`${claseBotonSecundario} mt-3 text-sm`}
                        >Actualizar estado</button>
                      </div>
                    )}
                    {(pestania === 'esperando_ofertas' || pestania === 'esperando_adjudicacion' || pestania === 'en_proceso') && (
                      <PanelAdjudicacion
                        ofertas={ofertasPorEmergencia[emergencia.id]}
                        lotes={emergencia.lotes}
                        cargando={cargandoOfertas[emergencia.id] === true}
                        errorCarga={errorOfertas[emergencia.id]}
                        adjudicando={adjudicando[emergencia.id] ?? null}
                        finalizando={finalizando[emergencia.id] ?? null}
                        errorAdjudicar={errorAdjudicar}
                        exitoAdjudicar={exitoAdjudicar}
                        errorFinalizar={errorFinalizar}
                        exitoFinalizar={exitoFinalizar}
                        alAdjudicar={(ofertaId, paraSeleccion) => void manejarAdjudicar(emergencia.id, ofertaId, paraSeleccion)}
                        alFinalizar={(ofertaId) => void manejarFinalizarOferta(emergencia.id, ofertaId)}
                        evaluando={pestania === 'esperando_ofertas' || evaluacionBloquea(emergencia.id)}
                        confirmando={confirmando[emergencia.id] === true}
                        confirmada={confirmadas[emergencia.id] === true}
                        errorConfirmar={errorConfirmar[emergencia.id]}
                        exitoConfirmar={exitoConfirmar[emergencia.id]}
                        alConfirmar={() => void manejarConfirmarSeleccion(emergencia.id)}
                        puedeAdjudicar={pestania === 'esperando_adjudicacion'}
                        puedeConfirmar={pestania === 'esperando_adjudicacion'}
                      />
                    )}

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

                          <CamposLote
                            prefijo={`lote-${emergencia.id}`}
                            borrador={borrador}
                            deshabilitado={guardandoLote}
                            error={errorFormulario}
                            sugerencias={
                              (busquedasRecursos[emergencia.id] ?? BUSQUEDA_RECURSO_VACIA)
                                .sugerencias
                            }
                            cargandoRecursos={
                              (busquedasRecursos[emergencia.id] ?? BUSQUEDA_RECURSO_VACIA)
                                .cargando
                            }
                            errorRecursos={
                              (busquedasRecursos[emergencia.id] ?? BUSQUEDA_RECURSO_VACIA)
                                .error
                            }
                            creandoRecurso={
                              (busquedasRecursos[emergencia.id] ?? BUSQUEDA_RECURSO_VACIA)
                                .creando
                            }
                            alBuscarRecurso={(texto) =>
                              void buscarRecursosParaNuevoLote(emergencia.id, texto)
                            }
                            alSeleccionarRecurso={(recurso) =>
                              seleccionarRecursoNuevo(emergencia.id, recurso)
                            }
                            alCrearRecurso={() =>
                              void crearRecursoParaNuevoLote(emergencia.id)
                            }
                            alCambiar={(campo, valor) =>
                              actualizarBorrador(emergencia.id, campo, valor)
                            }
                          />

                          <BotonEnviarLote
                            guardando={guardandoLote}
                            texto="Agregar lote"
                            textoGuardando="Guardando lote..."
                          />
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
                              publicando[emergencia.id]
                            }
                            className="rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-slate-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {publicando[emergencia.id]
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
