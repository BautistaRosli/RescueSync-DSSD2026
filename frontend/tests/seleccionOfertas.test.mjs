import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

const urlModulo = (codigo) => `data:text/javascript;base64,${Buffer.from(codigo).toString('base64')}`

async function transpilar(ruta, reemplazos = {}, prefijo = '') {
  const fuente = await readFile(new URL(ruta, import.meta.url), 'utf8')
  let codigo = ts.transpileModule(fuente, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023,
      jsx: ts.JsxEmit.React, jsxFactory: 'crearElemento', jsxFragmentFactory: 'Fragmento',
    },
  }).outputText
  for (const [origen, destino] of Object.entries(reemplazos)) {
    codigo = codigo.replaceAll(`'${origen}'`, JSON.stringify(destino))
      .replaceAll(JSON.stringify(origen), JSON.stringify(destino))
  }
  return urlModulo(prefijo + codigo)
}

const moduloHttp = await transpilar('../src/services/http.ts')
const { ApiError } = await import(moduloHttp)
const servicios = await import(await transpilar('../src/services/oferta.ts', { './http': moduloHttp }))
const serviciosEmergencia = await import(await transpilar('../src/services/emergencia.ts', { './http': moduloHttp }))
const prefijoJsx = 'function crearElemento(type, props, ...children){return {type,props:{...props,children}}} function Fragmento({children}){return children}\n'
const moduloClases = await transpilar('../src/ui/clases.ts')
const moduloFormato = await transpilar('../src/utils/formato.ts', {
  '../services': urlModulo(`export {ApiError} from ${JSON.stringify(moduloHttp)};`),
})
const moduloUtilOfertas = await transpilar('../src/utils/ofertas.ts')
// El panel compartido de adjudicación reemplaza al barrel de componentes en las páginas.
const moduloComponentes = await transpilar('../src/components/PanelAdjudicacion.tsx', {
  '../ui/clases': moduloClases, '../utils/formato': moduloFormato, '../utils/ofertas': moduloUtilOfertas,
}, prefijoJsx)

test('Las ofertas del coordinador usan la consulta por emergencia con la evaluación Cloud', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null } })
  const respuesta = [{ id: 12, puede_seleccionar: false, estado_seleccion: 'sin_seleccionar', items: [{ cantidad_verificada: 0 }] }]
  const peticiones = []
  globalThis.fetch = async (url, opciones) => {
    peticiones.push({ url, metodo: opciones.method })
    return new Response(JSON.stringify(respuesta))
  }
  try {
    assert.deepEqual(await servicios.listarOfertasDeEmergencia(7), respuesta)
    await servicios.listarOfertasDeOrganizacion(8)
    assert.deepEqual(peticiones, [
      { url: 'http://localhost:8000/api/v1/emergencias/7/ofertas', metodo: 'GET' },
      { url: 'http://localhost:8000/api/v1/ofertas', metodo: 'GET' },
    ])
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

test('Adjudicar prepara selecciones con paraSeleccion y sin enviar cuerpo', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true, value: { getItem: () => 'token-prueba' },
  })
  const peticiones = []
  globalThis.fetch = async (url, opciones) => {
    peticiones.push({ url, opciones })
    return new Response(JSON.stringify({ oferta_id: 12, mensaje: 'Operación registrada.' }))
  }
  try {
    for (const argumentos of [[12, true]]) {
      assert.deepEqual(await servicios.adjudicarOferta(...argumentos), {
        oferta_id: 12, mensaje: 'Operación registrada.',
      })
    }
    assert.deepEqual(peticiones.map(({ url }) => url), [
      'http://localhost:8000/api/v1/ofertas/12/adjudicar?para_seleccion=true',
    ])
    for (const { opciones } of peticiones) {
      assert.equal(opciones.method, 'POST')
      assert.equal(opciones.body, undefined)
      assert.equal(opciones.headers.Authorization, 'Bearer token-prueba')
    }
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

test('Confirmar selección envía POST sin cuerpo y conserva la respuesta y el rechazo', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true, value: { getItem: () => 'token-prueba' },
  })
  const respuesta = { emergencia_id: 1, cantidad_pares: 2, ya_confirmada: true }
  let rechazar = false
  globalThis.fetch = async (url, opciones) => {
    assert.equal(url, 'http://localhost:8000/api/v1/emergencias/1/confirmar-seleccion')
    assert.equal(opciones.method, 'POST')
    assert.equal(opciones.body, undefined)
    assert.equal(opciones.headers.Authorization, 'Bearer token-prueba')
    return new Response(JSON.stringify(rechazar ? { detail: 'Selección diferente.' } : respuesta), {
      status: rechazar ? 409 : 200,
    })
  }
  try {
    assert.deepEqual(await servicios.confirmarSeleccionOfertas(1), respuesta)
    rechazar = true
    await assert.rejects(servicios.confirmarSeleccionOfertas(1), {
      status: 409, detail: 'Selección diferente.',
    })
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

function diferida() {
  let resolver, rechazar
  const promesa = new Promise((resolve, reject) => { resolver = resolve; rechazar = reject })
  return { promesa, resolver, rechazar }
}

async function montarPagina({ componente = 'coordinador', estado = 'esperando_adjudicacion', conMarca = true, evaluaciones = [3], puedeSeleccionar = true, estadoSeleccion = 'seleccionada_para_confirmar', tareas = {}, sinOfertas = false, consultaEvaluacion, sincronizar, itemsFinalizados = false, prepararOfertas } = {}) {
  const estados = [], referencias = [], efectos = [], dependencias = [], limpiezas = []
  let indiceEstado = 0, indiceRef = 0, indiceEfecto = 0
  const oferta = (id, emergencia_id, adjudicada_en = null) => ({
    id, emergencia_id, adjudicada_en, organizacion_id: id, organizaciones: [],
    fecha_hora_oferta: '2026-11-21T10:00:00Z',
    estado_seleccion: adjudicada_en ? estadoSeleccion : 'sin_seleccionar',
    puede_seleccionar: adjudicada_en === null && puedeSeleccionar,
    items: evaluaciones.map((cantidad_verificada, indice) => ({
      id: id * 10 + indice, lote_necesidad_id: id * 10 + indice,
      cantidad_ofrecida: 8, cantidad_verificada, descripcion: null, finalizado_en: itemsFinalizados ? '2026-11-21T10:00:00Z' : null,
    })),
  })
  const emergencias = [1, 2].map((id) => ({
    id, nombre: `Emergencia ${id}`, descripcion: '', ubicacion: '', gravedad: 'baja',
    nivel_gravedad: 'baja', estado: estado === 'esperando_evaluacion' ? 'esperando_adjudicacion' : estado, etapa: estado, publicada: true,
    fecha_hora: null, fecha_publicacion: null, lotes: [],
  }))
  const ofertas = {
    1: [oferta(11, 1, conMarca ? '2026-11-20T10:00:00Z' : null), oferta(12, 1), oferta(13, 1)],
    2: [oferta(21, 2)],
  }
  if (sinOfertas) ofertas[1] = []
  prepararOfertas?.(ofertas)
  const llamadas = { adjudicar: [], confirmar: [], finalizar: [], sincronizar: [], listar: [], consultarEvaluacion: [], consultarSeleccion: [], evaluar: [], bandeja: [], orden: [] }
  const control = {
    ofertas, emergencias, tareas, seleccionLista: {},
    consultarEvaluacion: consultaEvaluacion ?? (async (id, incluirSeleccion) => ({ tarea_id: tareas[id] ?? null, ...(incluirSeleccion ? { seleccion_oferta_lista: control.seleccionLista[id] === true } : {}) })),
    evaluar: async (id, datos) => ({ tarea_id: datos.tarea_id }),
    async obtenerEmergencia(id) { return structuredClone(emergencias.find((item) => item.id === id)) },
    async obtenerEvaluacionProyecto(id, incluirSeleccion) { llamadas.consultarEvaluacion.push(id); llamadas.consultarSeleccion.push(incluirSeleccion === true); return control.consultarEvaluacion(id, incluirSeleccion) },
    async evaluarProyecto(id, datos) { llamadas.evaluar.push({ id, datos }); return control.evaluar(id, datos) },
    adjudicar: async (id) => ({ oferta_id: id, mensaje: 'Seleccionada para confirmar' }),
    confirmar: async (id) => ({ emergencia_id: id, cantidad_pares: 2, ya_confirmada: false }),
    finalizar: async (id) => ({ oferta_id: id, estado: 'finalizada', mensaje: 'Bonita continúa para liberar recursos Cloud.' }),
    sincronizar: sincronizar ?? (async () => ({ emergencias_resueltas: [] })),
    async sincronizarCierresEmergencias() {
      llamadas.sincronizar.push(true)
      llamadas.orden.push('sincronizar')
      return control.sincronizar(emergencias)
    },
    async finalizarOferta(id) { llamadas.finalizar.push(id); return control.finalizar(id) },
    useState(inicial) {
      const indice = indiceEstado++
      if (!(indice in estados)) estados[indice] = typeof inicial === 'function' ? inicial() : inicial
      return [estados[indice], (valor) => {
        estados[indice] = typeof valor === 'function' ? valor(estados[indice]) : valor
      }]
    },
    useRef(inicial) {
      const indice = indiceRef++
      return referencias[indice] ??= { current: inicial }
    },
    useCallback(funcion, deps) {
      const referencia = control.useRef({ funcion, deps })
      if (deps.some((valor, indice) => valor !== referencia.current.deps[indice])) referencia.current = { funcion, deps }
      return referencia.current.funcion
    },
    useEffect(efecto, deps) {
      const indice = indiceEfecto++
      if (!dependencias[indice] || deps.some((valor, i) => valor !== dependencias[indice][i])) {
        dependencias[indice] = deps
        efectos.push(() => { limpiezas[indice]?.(); limpiezas[indice] = efecto() })
      }
    },
    async listarBandejaEmergencias(params) {
      llamadas.bandeja.push(params)
      llamadas.orden.push(`bandeja:${params.estado ?? params.etapa_bonita}`)
      const items = emergencias.filter((emergencia) => params.etapa_bonita ? emergencia.etapa === params.etapa_bonita : emergencia.estado === params.estado)
      return { items, paginas: 1, pagina: 1, total: items.length }
    },
    consultarOfertas: async (id) => structuredClone(ofertas[id]),
    async listarOfertasDeEmergencia(id) { llamadas.listar.push(id); return control.consultarOfertas(id) },
    async adjudicarOferta(id, paraSeleccion) {
      llamadas.adjudicar.push({ id, paraSeleccion })
      const respuesta = await control.adjudicar(id)
      if (respuesta.oferta_id === id) {
        const registro = Object.values(ofertas).flat().find((oferta) => oferta.id === id)
        registro.adjudicada_en = '2026-11-21T10:00:00Z'
        registro.puede_seleccionar = false
        registro.estado_seleccion = paraSeleccion ? 'seleccionada_para_confirmar' : 'adjudicada'
        if (!paraSeleccion) Object.assign(emergencias.find((item) => item.id === registro.emergencia_id), { estado: 'en_proceso', etapa: 'en_proceso' })
      }
      return respuesta
    },
    async confirmarSeleccionOfertas(id) {
      llamadas.confirmar.push(id)
      const respuesta = await control.confirmar(id)
      if (respuesta.emergencia_id === id) {
        Object.assign(emergencias.find((item) => item.id === id), { estado: 'en_proceso', etapa: 'en_proceso' })
        for (const oferta of ofertas[id]) {
          oferta.puede_seleccionar = false
          if (oferta.adjudicada_en) oferta.estado_seleccion = 'adjudicada'
        }
      }
      return respuesta
    },
  }
  const clave = `__seleccion_${Math.random().toString(36).slice(2)}`
  globalThis[clave] = control
  const acceso = `globalThis[${JSON.stringify(clave)}]`
  const hooks = urlModulo(['useState', 'useRef', 'useEffect', 'useCallback'].map((nombre) =>
    `export const ${nombre}=(...args)=>${acceso}.${nombre}(...args);`).join('\n'))
  const nombresServicios = [
    'actualizarLote', 'adjudicarOferta', 'confirmarSeleccionOfertas', 'crearLote',
    'eliminarLote', 'listarBandejaEmergencias', 'listarOfertasDeEmergencia', 'publicarEmergencia',
    'listarRecursosCloud', 'crearRecursoCloud', 'obtenerEmergencia', 'obtenerEvaluacionProyecto', 'evaluarProyecto',
    'finalizarOferta', 'sincronizarCierresEmergencias',
  ]
  const moduloServicios = urlModulo(`export {ApiError} from ${JSON.stringify(moduloHttp)};\n` +
    nombresServicios.map((nombre) =>
      `export const ${nombre}=(...args)=>${acceso}.${nombre}(...args);`).join('\n'))
  const moduloPagina = componente === 'municipio'
    ? await transpilar('../src/pages/AdjudicacionMunicipioPage.tsx', {
      react: hooks, '../services': moduloServicios, '../components': moduloComponentes,
      '../ui/clases': moduloClases, '../utils/formato': moduloFormato,
    }, prefijoJsx)
    : await transpilar('../src/pages/CentroCoordinadorPage.tsx', {
      react: hooks, '../services': moduloServicios, '../components': moduloComponentes,
      './formularioLote': await transpilar('../src/pages/formularioLote.ts'),
      '../ui/clases': moduloClases, '../utils/ofertas': moduloUtilOfertas,
    }, prefijoJsx)
  const modulo = await import(moduloPagina)
  const Pagina = componente === 'municipio' ? modulo.AdjudicacionMunicipioPage : modulo.CentroCoordinadorPage
  function aplanar(nodo) {
    if (nodo == null || typeof nodo === 'boolean') return []
    if (Array.isArray(nodo)) return nodo.flatMap(aplanar)
    if (typeof nodo !== 'object') return [nodo]
    if (typeof nodo.type === 'function') return aplanar(nodo.type(nodo.props))
    return [nodo, ...aplanar(nodo.props.children)]
  }
  function renderizar() {
    indiceEstado = 0; indiceRef = 0; indiceEfecto = 0
    return aplanar(Pagina())
  }
  const texto = (nodo) => aplanar(nodo.props.children).filter((valor) => typeof valor !== 'object').join('')
  const botones = (etiqueta) => renderizar().filter((nodo) => nodo.type === 'button' && texto(nodo) === etiqueta)
  async function asentar() {
    renderizar()
    for (const efecto of efectos.splice(0)) efecto()
    await new Promise((resolve) => setImmediate(resolve))
  }
  await asentar()
  const etiqueta = { esperando_evaluacion: 'Esperando Evaluacion', esperando_adjudicacion: 'Esperando adjudicación', en_proceso: 'En proceso', esperando_ofertas: 'Esperando ofertas', esperando_lotes: 'Esperando lotes', resuelta: 'Resueltas' }[estado]
  botones(etiqueta)[0].props.onClick()
  await asentar()
  const filas = renderizar().filter((nodo) => nodo.type === 'button' && nodo.props['aria-expanded'] === false)
  for (const fila of filas) fila.props.onClick()
  await asentar()
  const ventanaOriginal = globalThis.window
  globalThis.window = { confirm: () => true }
  return { control, llamadas, botones, renderizar, texto, asentar, limpiar: () => {
    for (const limpiar of limpiezas) limpiar?.()
    delete globalThis[clave]
    if (ventanaOriginal === undefined) delete globalThis.window
    else globalThis.window = ventanaOriginal
  } }
}

test('Sincronizar cierres usa POST autenticado sin cuerpo y conserva el error de servicio', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'token-prueba' } })
  let fallar = false
  globalThis.fetch = async (url, opciones) => {
    assert.equal(url, 'http://localhost:8000/api/v1/emergencias/sincronizar-cierres')
    assert.equal(opciones.method, 'POST')
    assert.equal(opciones.body, undefined)
    assert.equal(opciones.headers.Authorization, 'Bearer token-prueba')
    return new Response(JSON.stringify(fallar ? { detail: 'Bonita no disponible.' } : { emergencias_resueltas: [1] }), { status: fallar ? 503 : 200 })
  }
  try {
    assert.deepEqual(await serviciosEmergencia.sincronizarCierresEmergencias(), { emergencias_resueltas: [1] })
    fallar = true
    await assert.rejects(serviciosEmergencia.sincronizarCierresEmergencias(), { status: 503 })
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

const opcionesCierre = { estado: 'en_proceso', estadoSeleccion: 'adjudicada', itemsFinalizados: true }
const pestaniaActiva = (pagina, etiqueta) => pagina.botones(etiqueta)[0].props['aria-current'] === 'page'
const mensajesCierre = (pagina) => pagina.renderizar().filter((nodo) => nodo.props?.role === 'status' || nodo.props?.role === 'alert').map(pagina.texto).join(' ')

test('El cierre espera los ítems de todas las ofertas adjudicadas de la emergencia', async () => {
  for (const vacia of [false, true]) {
    const pagina = await montarPagina({ ...opcionesCierre, prepararOfertas(ofertas) {
      ofertas[1][1].estado_seleccion = 'adjudicada'
      ofertas[1][1].adjudicada_en = '2026-11-21T10:00:00Z'
      if (vacia) ofertas[1][1].items = []
      else ofertas[1][1].items[0].finalizado_en = null
    } })
    try {
      assert.equal(pagina.botones('Cerrar oferta').length, 0)
      assert.match(mensajesCierre(pagina), /Todavía hay ofertas adjudicadas con ítems pendientes de finalización\./)
      assert.deepEqual(pagina.llamadas.finalizar, [])
      assert.ok(pestaniaActiva(pagina, 'En proceso'))
    } finally { pagina.limpiar() }
  }
})

test('Todas las adjudicadas completas permiten cerrar aunque otras ofertas o emergencias estén pendientes', async () => {
  const pagina = await montarPagina({ ...opcionesCierre, prepararOfertas(ofertas) {
    ofertas[1][1].estado_seleccion = 'adjudicada'
    ofertas[1][1].adjudicada_en = '2026-11-21T10:00:00Z'
    ofertas[1][2].items[0].finalizado_en = null
    ofertas[2][0].estado_seleccion = 'adjudicada'
    ofertas[2][0].adjudicada_en = '2026-11-21T10:00:00Z'
    ofertas[2][0].items[0].finalizado_en = null
  } })
  try {
    assert.equal(pagina.botones('Cerrar oferta').length, 2)
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
    assert.match(mensajesCierre(pagina), /Se registró el cierre de la oferta\./)
  } finally { pagina.limpiar() }
})

test('Una selección provisional con fecha no habilita cierre ni bloquea las adjudicadas completas', async () => {
  for (const finalizada of [false, true]) {
    const pagina = await montarPagina({ ...opcionesCierre, prepararOfertas(ofertas) {
      ofertas[1][1].estado_seleccion = 'seleccionada_para_confirmar'
      ofertas[1][1].adjudicada_en = '2026-11-21T10:00:00Z'
      if (!finalizada) ofertas[1][1].items[0].finalizado_en = null
    } })
    try {
      assert.equal(pagina.botones('Cerrar oferta').length, 1)
      assert.doesNotMatch(mensajesCierre(pagina), /ítems pendientes/)
      pagina.botones('Cerrar oferta')[0].props.onClick()
      await pagina.asentar()
      assert.deepEqual(pagina.llamadas.finalizar, [11])
    } finally { pagina.limpiar() }
  }
})

test('Las ofertas antiguas sin estado conservan su cierre por adjudicada_en', async () => {
  const pagina = await montarPagina({ ...opcionesCierre, prepararOfertas(ofertas) {
    delete ofertas[1][0].estado_seleccion
  } })
  try {
    assert.equal(pagina.botones('Cerrar oferta').length, 1)
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
  } finally { pagina.limpiar() }
})

test('Un manejador retenido vuelve a comprobar todas las adjudicadas después de recargar', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    const cerrar = pagina.botones('Cerrar oferta')[0].props.onClick
    pagina.control.ofertas[1][1].estado_seleccion = 'adjudicada'
    pagina.control.ofertas[1][1].adjudicada_en = '2026-11-21T10:00:00Z'
    pagina.control.ofertas[1][1].items[0].finalizado_en = null
    cerrar()
    await pagina.asentar()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
    cerrar()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
  } finally { pagina.limpiar() }
})

test('Un cierre confirmado muestra un mensaje apropiado y abre Resueltas solo para su emergencia', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    assert.equal(pagina.botones('Cerrar oferta y liberar recursos').length, 0)
    const cierre = diferida()
    pagina.control.finalizar = () => cierre.promesa
    const boton = pagina.botones('Cerrar oferta')[0]
    boton.props.onClick()
    boton.props.onClick()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
    pagina.control.sincronizar = async (emergencias) => {
      emergencias[0].estado = 'resuelta'
      return { emergencias_resueltas: [1] }
    }
    cierre.resolver({ oferta_id: 11, estado: 'finalizada', mensaje: 'Bonita continúa para liberar recursos Cloud.' })
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'Resueltas'))
    assert.equal(mensajesCierre(pagina), 'La emergencia fue resuelta')
    assert.doesNotMatch(mensajesCierre(pagina), /Bonita|Cloud|liberar/)
    assert.equal(pagina.control.emergencias[0].estado, 'resuelta')
    assert.equal(pagina.control.emergencias[1].estado, 'en_proceso')
  } finally { pagina.limpiar() }
})

test('Al cargar En proceso o Resueltas se sincronizan los cierres antes de listar y se conserva la pestaña elegida', async () => {
  for (const estado of ['en_proceso', 'resuelta']) {
    const pagina = await montarPagina({ estado, sincronizar: async (emergencias) => {
      emergencias[0].estado = 'resuelta'
      emergencias[1].estado = 'en_proceso'
      return { emergencias_resueltas: [1] }
    } })
    try {
      assert.ok(pestaniaActiva(pagina, estado === 'resuelta' ? 'Resueltas' : 'En proceso'))
      const posicion = pagina.llamadas.orden.indexOf(`bandeja:${estado}`)
      assert.equal(pagina.llamadas.orden[posicion - 1], 'sincronizar')
      const filas = pagina.renderizar().filter((nodo) => nodo.type === 'button' && nodo.props['aria-expanded'] !== undefined)
      assert.equal(filas.length, 1)
      assert.match(pagina.texto(filas[0]), estado === 'resuelta' ? /#1/ : /#2/)
    } finally { pagina.limpiar() }
  }
})

test('Un cierre pendiente conserva En proceso y no muestra detalles del motor', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.equal(pagina.control.emergencias[0].estado, 'en_proceso')
    assert.match(mensajesCierre(pagina), /Se registró el cierre de la oferta\./)
    assert.doesNotMatch(mensajesCierre(pagina), /Bonita|Cloud|Resueltas/)
  } finally { pagina.limpiar() }
})

test('Una sincronización idempotente confirma el estado persistido de la misma emergencia', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    pagina.control.sincronizar = async (emergencias) => {
      emergencias[0].estado = 'resuelta'
      return { emergencias_resueltas: [] }
    }
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'Resueltas'))
  } finally { pagina.limpiar() }
})

test('Un 503 al sincronizar permite listar y ofrece reintentar sin anunciar resolución', async () => {
  const pagina = await montarPagina({ ...opcionesCierre, sincronizar: async () => { throw new ApiError(503, 'Bonita no disponible.') } })
  try {
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.equal(pagina.botones('Cerrar oferta').length, 1)
    assert.match(mensajesCierre(pagina), /Recargá la bandeja/)
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.equal(pagina.control.emergencias[0].estado, 'en_proceso')
    assert.doesNotMatch(mensajesCierre(pagina), /Bonita|Cloud|La emergencia fue resuelta/)
  } finally { pagina.limpiar() }
})

test('El cierre de otra emergencia o una consulta con otro ID no anuncia la resolución del caso actual', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    pagina.control.sincronizar = async () => ({ emergencias_resueltas: [2] })
    pagina.control.obtenerEmergencia = async () => ({ id: 2, estado: 'resuelta' })
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.doesNotMatch(mensajesCierre(pagina), /La emergencia fue resuelta/)
  } finally { pagina.limpiar() }
})

test('Una sincronización tardía del cierre no navega ni avisa en otra pestaña', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    const sincronizacion = diferida()
    pagina.control.sincronizar = () => sincronizacion.promesa
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    pagina.botones('Esperando lotes')[0].props.onClick()
    await pagina.asentar()
    sincronizacion.resolver({ emergencias_resueltas: [1] })
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'Esperando lotes'))
    assert.doesNotMatch(mensajesCierre(pagina), /La emergencia fue resuelta/)
  } finally { pagina.limpiar() }
})

test('Un rechazo del cierre conserva el caso activo y permite reintentar con un error apropiado', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    pagina.control.finalizar = async () => { throw new ApiError(503, 'Bonita: tarea no disponible; Cloud pendiente.') }
    pagina.botones('Cerrar oferta')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.equal(pagina.botones('Cerrar oferta').length, 1)
    assert.match(mensajesCierre(pagina), /No se pudo cerrar la oferta\. Intentá de nuevo\./)
    assert.doesNotMatch(mensajesCierre(pagina), /Bonita|Cloud|Se registró/)
  } finally { pagina.limpiar() }
})

test('Una respuesta tardía del cierre no cambia la pestaña después de salir y volver', async () => {
  const pagina = await montarPagina(opcionesCierre)
  try {
    const cierre = diferida()
    pagina.control.finalizar = () => cierre.promesa
    const boton = pagina.botones('Cerrar oferta')[0]
    boton.props.onClick()
    pagina.botones('Esperando lotes')[0].props.onClick()
    await pagina.asentar()
    boton.props.onClick()
    assert.deepEqual(pagina.llamadas.finalizar, [11])
    pagina.botones('En proceso')[0].props.onClick()
    await pagina.asentar()
    pagina.control.sincronizar = async (emergencias) => {
      emergencias[0].estado = 'resuelta'
      return { emergencias_resueltas: [1] }
    }
    cierre.resolver({ oferta_id: 11, estado: 'finalizada', mensaje: 'Cierre registrado.' })
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pestaniaActiva(pagina, 'En proceso'))
    assert.doesNotMatch(mensajesCierre(pagina), /La emergencia fue resuelta/)
  } finally { pagina.limpiar() }
})

test('La selección bloquea duplicados, respeta adjudicaciones persistidas y permite reintentar por emergencia', async () => {
  const pagina = await montarPagina({ componente: 'municipio', componente: 'municipio' })
  try {
    assert.equal(pagina.botones('Confirmar selección').length, 2)
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    assert.equal(pagina.botones('Seleccionada para confirmar')[0].props.disabled, true)
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    assert.equal(pagina.botones('Confirmar selección')[1].props.disabled, true)
    pagina.botones('Confirmar selección')[1].props.onClick()
    assert.deepEqual(pagina.llamadas.confirmar, [])
    const pendiente = diferida()
    pagina.control.adjudicar = () => pendiente.promesa
    const adjudicar = pagina.botones('Adjudicar')[0]
    adjudicar.props.onClick()
    adjudicar.props.onClick()
    pagina.botones('Confirmar selección')[0].props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [{ id: 12, paraSeleccion: true }])
    assert.deepEqual(pagina.llamadas.confirmar, [])
    assert.equal(pagina.botones('Confirmar selección')[0].props.disabled, true)
    pendiente.resolver({ oferta_id: 12, mensaje: 'Correo enviado.' })
    await pagina.asentar()
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 2)
    adjudicar.props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [{ id: 12, paraSeleccion: true }])
    const confirmacion = diferida()
    pagina.control.confirmar = () => confirmacion.promesa
    const confirmar = pagina.botones('Confirmar selección')[0]
    confirmar.props.onClick()
    confirmar.props.onClick()
    assert.deepEqual(pagina.llamadas.confirmar, [1])
    assert.equal(pagina.botones('Confirmando selección...').length, 1)
    assert.equal(pagina.botones('Adjudicar')[0].props.disabled, true)
    assert.equal(pagina.botones('Adjudicar')[1].props.disabled, false)
    pagina.botones('Adjudicar')[0].props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [{ id: 12, paraSeleccion: true }])
    confirmacion.rechazar(new ApiError(503, 'Bonita no disponible.'))
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'Bonita no disponible.'))
    pagina.control.confirmar = async (id) => ({ emergencia_id: id, cantidad_pares: 2, ya_confirmada: true })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.confirmar, [1, 1])
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /ya estaba confirmada/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Confirmar selección').length, 0)
    assert.equal(pagina.botones('Adjudicar').length, 0)
    confirmar.props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [{ id: 12, paraSeleccion: true }])
    assert.deepEqual(pagina.llamadas.confirmar, [1, 1])
  } finally { pagina.limpiar() }
})

test('Una adjudicación rechazada no marca la oferta y una respuesta de otra selección no anuncia éxito', async () => {
  const pagina = await montarPagina({ componente: 'municipio', componente: 'municipio' })
  try {
    pagina.control.adjudicar = async () => { throw new ApiError(409, 'No se pudo adjudicar.') }
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'No se pudo adjudicar.'))
    pagina.control.adjudicar = async () => ({ oferta_id: 99, mensaje: 'Correo enviado.' })
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && /respuesta de adjudicación/.test(pagina.texto(nodo))))
    pagina.control.confirmar = async () => ({ emergencia_id: 99, cantidad_pares: 2, ya_confirmada: false })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Selección confirmada').length, 0)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && /respuesta/.test(pagina.texto(nodo))))
    pagina.control.confirmar = async (id) => ({ emergencia_id: id, cantidad_pares: 1, ya_confirmada: false })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /Selección confirmada correctamente/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Adjudicar').length, 0)
  } finally { pagina.limpiar() }
})

test('En proceso no ofrece confirmar la selección aunque existan adjudicaciones persistidas', async () => {
  const pagina = await montarPagina({ componente: 'municipio', estado: 'en_proceso' })
  try {
    assert.equal(pagina.botones('Confirmar selección').length, 0)
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    assert.deepEqual(pagina.llamadas.confirmar, [])
  } finally { pagina.limpiar() }
})

test('El municipio consulta las emergencias publicadas por estado y avisa si no hay ofertas validadas', async () => {
  for (const estado of ['esperando_adjudicacion', 'en_proceso']) {
    const pagina = await montarPagina({ componente: 'municipio', estado, sinOfertas: true })
    try {
      const etapa = estado === 'esperando_adjudicacion' ? { etapa_bonita: 'esperando_adjudicacion' } : {}
      assert.deepEqual(pagina.llamadas.bandeja.at(-1), { publicada: true, estado, ...etapa, pagina: 1, por_pagina: 10 })
      assert.ok(pagina.llamadas.bandeja.every((consulta) => consulta.publicada === true &&
        consulta.etapa_bonita === (consulta.estado === 'esperando_adjudicacion' ? 'esperando_adjudicacion' : undefined)))
      assert.deepEqual(pagina.llamadas.sincronizar, [])
      assert.deepEqual(pagina.llamadas.consultarEvaluacion, [])
      assert.equal(pagina.botones(estado === 'en_proceso' ? 'En proceso' : 'Esperando adjudicación')[0].props['aria-current'], 'page')
      assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'p' &&
        pagina.texto(nodo) === 'Todavía no hay ofertas validadas por el Sistema Nacional para esta emergencia.'))
      assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'span' && pagina.texto(nodo) === 'Verificado por el Sistema Nacional: 3'))
      assert.equal(pagina.botones('Cerrar oferta').length, 0)
    } finally { pagina.limpiar() }
  }
})

test('El coordinador ve las ofertas sin adjudicar ni confirmar y conserva el cierre', async () => {
  for (const estado of ['esperando_adjudicacion', 'en_proceso']) {
    const pagina = await montarPagina({ estado, conMarca: false, itemsFinalizados: true, estadoSeleccion: 'adjudicada',
      prepararOfertas: (ofertas) => { if (estado === 'en_proceso') Object.assign(ofertas[1][0], { adjudicada_en: '2026-11-20T10:00:00Z', estado_seleccion: 'adjudicada', puede_seleccionar: false }) } })
    try {
      assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'span' && pagina.texto(nodo) === 'Oferta #12'))
      assert.equal(pagina.renderizar().filter((nodo) => nodo.props?.role === 'note' && pagina.texto(nodo) === 'La adjudicación la realiza el municipio.').length, 2)
      for (const etiqueta of ['Adjudicar', 'Confirmar selección']) {
        assert.equal(pagina.botones(etiqueta).length, 0, etiqueta)
      }
      assert.equal(pagina.botones('Cerrar oferta').length, estado === 'en_proceso' ? 1 : 0)
      assert.deepEqual(pagina.llamadas.adjudicar, [])
      assert.deepEqual(pagina.llamadas.confirmar, [])
    } finally { pagina.limpiar() }
  }
})

test('Se pueden preparar varias ofertas para confirmar la selección', async () => {
  const pagina = await montarPagina({ componente: 'municipio', conMarca: false })
  try {
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.adjudicar, [
      { id: 11, paraSeleccion: true }, { id: 12, paraSeleccion: true },
    ])
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 2)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.children && pagina.texto(nodo).includes('Estado: Esperando adjudicación')))
  } finally { pagina.limpiar() }
})

test('La evaluación muestra cero, pendiente o valor real y respeta la habilitación del servidor', async () => {
  for (const { evaluaciones, puedeSeleccionar, mensaje } of [
    { evaluaciones: [0], puedeSeleccionar: false, mensaje: 'Verificado por el Sistema Nacional: 0' },
    { evaluaciones: [null], puedeSeleccionar: false, mensaje: 'Pendiente de evaluación' },
    { evaluaciones: [4, 0], puedeSeleccionar: false, mensaje: 'Verificado por el Sistema Nacional: 4' },
    { evaluaciones: [4], puedeSeleccionar: false, mensaje: 'La selección no está habilitada en la etapa actual.' },
    { evaluaciones: [4], puedeSeleccionar: true, mensaje: 'Verificado por el Sistema Nacional: 4' },
  ]) {
    const pagina = await montarPagina({ componente: 'municipio', conMarca: false, evaluaciones, puedeSeleccionar })
    try {
      assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'span' || nodo.type === 'p'
        ? pagina.texto(nodo) === mensaje : false), mensaje)
      const boton = pagina.botones('Adjudicar')[0]
      assert.equal(boton.props.disabled, !puedeSeleccionar)
      boton.props.onClick()
      assert.equal(pagina.llamadas.adjudicar.length, puedeSeleccionar ? 1 : 0)
      await pagina.asentar()
    } finally { pagina.limpiar() }
  }
})

test('Una marca provisional sobrevive a la recarga y la confirmación refresca su estado final', async () => {
  const pagina = await montarPagina({ componente: 'municipio', puedeSeleccionar: false })
  try {
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    assert.equal(pagina.renderizar().filter((nodo) => nodo.type === 'p' && /Oferta adjudicada/.test(pagina.texto(nodo))).length, 0)
    assert.equal(pagina.botones('Confirmar selección')[0].props.disabled, false)
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pagina.llamadas.listar.filter((id) => id === 1).length >= 2)
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 0)
    assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'p' && /Oferta adjudicada/.test(pagina.texto(nodo))))
  } finally { pagina.limpiar() }
  const final = await montarPagina({ componente: 'municipio', estado: 'en_proceso', estadoSeleccion: 'adjudicada', puedeSeleccionar: false })
  try {
    assert.equal(final.botones('Seleccionada para confirmar').length, 0)
    assert.ok(final.renderizar().some((nodo) => nodo.type === 'p' && /Oferta adjudicada/.test(final.texto(nodo))))
  } finally { final.limpiar() }
})

test('Un handler anterior respeta la habilitación actual después de un rechazo y recarga', async () => {
  const pagina = await montarPagina({ componente: 'municipio', conMarca: false })
  try {
    const anterior = pagina.botones('Adjudicar')[1]
    pagina.control.adjudicar = async () => {
      pagina.control.ofertas[1][1].puede_seleccionar = false
      throw new ApiError(409, 'Lote #110 pendiente de evaluación.')
    }
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'Lote #110 pendiente de evaluación.'))
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 0)
    anterior.props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [{ id: 11, paraSeleccion: true }])
  } finally { pagina.limpiar() }
})

test('La selección provisional no repite mensajes y se reemplaza por la adjudicación final', async () => {
  const pagina = await montarPagina({ componente: 'municipio', conMarca: false })
  try {
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.renderizar().filter((nodo) => nodo.type === 'p' && pagina.texto(nodo) === 'Seleccionada para confirmar').length, 0)
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.renderizar().filter((nodo) => nodo.props?.role === 'status' && pagina.texto(nodo) === 'Seleccionada para confirmar').length, 0)
    assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'p' && /Oferta adjudicada/.test(pagina.texto(nodo))))
  } finally { pagina.limpiar() }
})


test('La evaluación consulta la tarea y envía el contrato real sin transformar la acción', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'token-prueba' } })
  const peticiones = []
  globalThis.fetch = async (url, opciones) => {
    peticiones.push({ url, opciones })
    return new Response(JSON.stringify({ tarea_id: 101 }), { status: opciones.method === 'POST' ? 202 : 200 })
  }
  try {
    assert.deepEqual(await serviciosEmergencia.obtenerEvaluacionProyecto(1), { tarea_id: 101 })
    for (const accion of ['REABRIR', 'REFORMULAR', 'CONTINUAR_PARCIAL']) {
      assert.deepEqual(await serviciosEmergencia.evaluarProyecto(1, { tarea_id: 101, accion }), { tarea_id: 101 })
    }
    assert.ok(peticiones.every(({ url }) => url === 'http://localhost:8000/api/v1/emergencias/1/evaluacion-proyecto'))
    assert.equal(peticiones[0].opciones.method, 'GET')
    assert.deepEqual(peticiones.slice(1).map(({ opciones }) => ({ metodo: opciones.method, datos: JSON.parse(opciones.body), token: opciones.headers.Authorization })),
      ['REABRIR', 'REFORMULAR', 'CONTINUAR_PARCIAL'].map((accion) => ({ metodo: 'POST', datos: { tarea_id: 101, accion }, token: 'Bearer token-prueba' })))
    for (const status of [409, 503]) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Evaluación no disponible.' }), { status })
      await assert.rejects(serviciosEmergencia.evaluarProyecto(1, { tarea_id: 101, accion: 'REABRIR' }), (error) => error instanceof ApiError && error.status === status)
    }
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

test('La bandeja envía las etapas Bonita antes de paginar y conserva el sobre y los errores', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null } })
  const respuesta = { items: [{ id: 42, estado: 'esperando_adjudicacion' }], pagina: 2, por_pagina: 10, paginas: 4, total: 37 }
  let rechazar = false
  globalThis.fetch = async (url) => {
    const consulta = new URL(url).searchParams
    assert.equal(consulta.get('publicada'), 'true')
    assert.equal(consulta.get('pagina'), '2')
    assert.equal(consulta.get('por_pagina'), '10')
    assert.equal(consulta.get('estado'), null)
    assert.ok(['esperando_ofertas', 'esperando_evaluacion', 'esperando_adjudicacion'].includes(consulta.get('etapa_bonita')))
    return new Response(JSON.stringify(rechazar ? { detail: 'Bonita no disponible.' } : respuesta), { status: rechazar ? 503 : 200 })
  }
  try {
    for (const etapa_bonita of ['esperando_ofertas', 'esperando_evaluacion', 'esperando_adjudicacion']) {
      assert.deepEqual(await serviciosEmergencia.listarBandejaEmergencias({ publicada: true, etapa_bonita, pagina: 2, por_pagina: 10 }), respuesta)
    }
    rechazar = true
    await assert.rejects(serviciosEmergencia.listarBandejaEmergencias({ publicada: true, etapa_bonita: 'esperando_evaluacion', pagina: 2, por_pagina: 10 }), { status: 503 })
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
})

test('Las pestañas derivadas consultan etapas y la evaluación se muestra entre ofertas y adjudicación', async () => {
  for (const estado of ['esperando_lotes', 'esperando_ofertas', 'esperando_evaluacion', 'esperando_adjudicacion', 'en_proceso', 'resuelta']) {
    const pagina = await montarPagina({ estado, tareas: { 1: 101 } })
    try {
      const derivada = ['esperando_ofertas', 'esperando_evaluacion', 'esperando_adjudicacion'].includes(estado)
      const consulta = pagina.llamadas.bandeja.at(-1)
      assert.deepEqual(consulta, { publicada: estado !== 'esperando_lotes', ...(derivada ? { etapa_bonita: estado } : { estado }), pagina: 1, por_pagina: 10 })
      const navegacion = pagina.renderizar().filter((nodo) => nodo.type === 'nav')[0]
      const etiquetas = navegacion.props.children[0].map((nodo) => pagina.texto(nodo))
      assert.deepEqual(etiquetas.slice(1, 4), ['Esperando ofertas', 'Esperando Evaluacion', 'Esperando adjudicación'])
      if (estado === 'esperando_evaluacion') {
        assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'span' && pagina.texto(nodo) === 'Estado: Esperando Evaluacion'))
        assert.equal(pagina.botones('Adjudicar').length, 0)
        assert.equal(pagina.botones('Confirmar selección').length, 0)
        assert.deepEqual(pagina.llamadas.listar, [1])
      } else {
        assert.deepEqual(pagina.llamadas.consultarEvaluacion, [])
        if (estado === 'esperando_ofertas') assert.equal(pagina.botones('Confirmar selección').length, 0)
      }
    } finally { pagina.limpiar() }
  }
})

test('La consulta ampliada confirma la tarea de selección incluso sin ofertas locales', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null } })
  globalThis.fetch = async (url) => {
    assert.equal(url, 'http://localhost:8000/api/v1/emergencias/1/evaluacion-proyecto?incluir_seleccion=true')
    return new Response(JSON.stringify({ tarea_id: null, seleccion_oferta_lista: true }))
  }
  try {
    assert.deepEqual(await serviciosEmergencia.obtenerEvaluacionProyecto(1, true), { tarea_id: null, seleccion_oferta_lista: true })
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false })
  try {
    pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
    pagina.control.evaluar = async (id, datos) => {
      pagina.control.tareas[id] = null
      pagina.control.emergencias.find((item) => item.id === id).etapa = null
      return { tarea_id: datos.tarea_id }
    }
    pagina.botones('Confirmar decisión')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando Evaluacion')[0].props['aria-current'], 'page')
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /Esperando el siguiente paso/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Actualizar estado')[0].props.disabled, false)
    pagina.control.ofertas[1] = []
    pagina.control.seleccionLista[1] = true
    pagina.control.emergencias[0].etapa = 'esperando_adjudicacion'
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando adjudicación')[0].props['aria-current'], 'page')
    assert.equal(pagina.botones('Confirmar decisión').length, 0)
    assert.ok(pagina.llamadas.consultarSeleccion.includes(true))
  } finally { pagina.limpiar() }
})

test('El procesamiento pendiente conserva la fila para reconsultar aunque Bonita ya la quite de Evaluación', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 } })
  try {
    pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
    pagina.control.evaluar = async (id, datos) => {
      pagina.control.tareas[id] = null
      pagina.control.emergencias.find((item) => item.id === id).etapa = null
      return { tarea_id: datos.tarea_id }
    }
    const cargas = pagina.llamadas.bandeja.length
    pagina.botones('Confirmar decisión')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.llamadas.bandeja.length, cargas)
    assert.equal(pagina.botones('Actualizar estado').length, 2)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /Esperando el siguiente paso/.test(pagina.texto(nodo))))
    pagina.control.consultarEvaluacion = async () => { throw new ApiError(503, 'Bonita no disponible.') }
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Actualizar estado')[0].props.disabled, false)
    assert.equal(pagina.llamadas.bandeja.length, cargas)
    pagina.control.consultarEvaluacion = async () => ({ tarea_id: null, seleccion_oferta_lista: true })
    pagina.control.emergencias[0].etapa = 'esperando_adjudicacion'
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando adjudicación')[0].props['aria-current'], 'page')
    assert.equal(pagina.llamadas.evaluar.length, 1)
  } finally { pagina.limpiar() }
})

test('La bandeja real de adjudicación limpia tareas y decisiones pendientes anteriores', async () => {
  for (const aceptada of [false, true]) {
    const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, conMarca: false })
    try {
      if (aceptada) {
        pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
        pagina.botones('Confirmar decisión')[0].props.onClick()
        await pagina.asentar()
        await pagina.asentar()
      }
      pagina.control.tareas[1] = null
      pagina.control.emergencias[0].etapa = 'esperando_adjudicacion'
      pagina.botones('Esperando adjudicación')[0].props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      // El coordinador ve las ofertas, pero la adjudicación la realiza el municipio.
      assert.equal(pagina.botones('Esperando adjudicación')[0].props['aria-current'], 'page')
      assert.equal(pagina.botones('Confirmar decisión').length, 0)
      assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'span' && pagina.texto(nodo) === 'Oferta #11'))
      assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'note' && pagina.texto(nodo) === 'La adjudicación la realiza el municipio.'))
      assert.equal(pagina.botones('Adjudicar').length, 0)
      assert.deepEqual(pagina.llamadas.adjudicar, [])
    } finally { pagina.limpiar() }
  }
})

test('La bandeja no levanta el candado de una decisión realmente en vuelo', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, conMarca: false })
  try {
    const pendiente = diferida()
    pagina.control.evaluar = () => pendiente.promesa
    pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'REABRIR' } })
    pagina.botones('Confirmar decisión')[0].props.onClick()
    pagina.control.emergencias[0].etapa = 'esperando_adjudicacion'
    pagina.botones('Esperando adjudicación')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    // La fila sigue desplegada al cambiar de sección; las ofertas se cargan al abrirla.
    const fila = pagina.renderizar().find((nodo) => nodo.type === 'button' && nodo.props['aria-expanded'] === true)
    fila.props.onClick()
    await pagina.asentar()
    pagina.renderizar().find((nodo) => nodo.type === 'button' && nodo.props['aria-expanded'] === false).props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Adjudicar').length, 0)
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    pendiente.rechazar(new ApiError(503, 'Bonita no disponible.'))
    await pagina.asentar()
    await pagina.asentar()
  } finally { pagina.limpiar() }
})

test('Evaluar proyecto funciona sin ofertas y muestra las tres acciones únicamente con tarea lista', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, sinOfertas: true, puedeSeleccionar: false })
  try {
    assert.deepEqual(pagina.llamadas.consultarEvaluacion, [1, 2])
    assert.equal(pagina.botones('Confirmar decisión').length, 1)
    assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, true)
    pagina.botones('Confirmar decisión')[0].props.onClick()
    assert.deepEqual(pagina.llamadas.evaluar, [])
    const opciones = pagina.renderizar().filter((nodo) => nodo.type === 'option' && ['REABRIR', 'REFORMULAR', 'CONTINUAR_PARCIAL'].includes(nodo.props.value))
    assert.deepEqual(opciones.map((nodo) => [nodo.props.value, pagina.texto(nodo)]), [
      ['REABRIR', 'Reabrir convocatoria'], ['REFORMULAR', 'Reformular pedido'], ['CONTINUAR_PARCIAL', 'Continuar con cobertura parcial'],
    ])
  } finally { pagina.limpiar() }
  for (const estado of ['esperando_adjudicacion', 'esperando_ofertas', 'en_proceso']) {
    const sinTarea = await montarPagina({ estado })
    try {
      assert.equal(sinTarea.botones('Confirmar decisión').length, 0)
      assert.deepEqual(sinTarea.llamadas.consultarEvaluacion, [])
    } finally { sinTarea.limpiar() }
  }
})

test('La cobertura parcial exige una oferta completa elegible de la misma emergencia con cantidades verificadas positivas', async () => {
  for (const caso of [
    { sinOfertas: true },
    { evaluaciones: [0] },
    { evaluaciones: [null] },
    { evaluaciones: [4, 0] },
    { evaluaciones: [4, null] },
    { evaluaciones: [] },
    { prepararOfertas: (ofertas) => ofertas[1].forEach((oferta) => { oferta.estado_seleccion = 'seleccionada_para_confirmar' }) },
    { prepararOfertas: (ofertas) => ofertas[1].forEach((oferta) => { oferta.emergencia_id = 2 }) },
    { evaluaciones: [4, 2], disponible: true },
  ]) {
    const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false, ...caso })
    try {
      const opcion = pagina.renderizar().find((nodo) => nodo.type === 'option' && nodo.props.value === 'CONTINUAR_PARCIAL')
      assert.equal(opcion.props.disabled, !caso.disponible)
      assert.deepEqual(pagina.llamadas.listar, [1])
      const select = pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1')
      select.props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
      assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, !caso.disponible)
      pagina.botones('Confirmar decisión')[0].props.onClick()
      assert.equal(pagina.llamadas.evaluar.length, caso.disponible ? 1 : 0)
      if (!caso.disponible) {
        assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'p' && /No hay ofertas elegibles con cantidad verificada positiva/.test(pagina.texto(nodo))))
        for (const accion of ['REABRIR', 'REFORMULAR']) {
          select.props.onChange({ target: { value: accion } })
          assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, false)
        }
      }
      await pagina.asentar()
    } finally { pagina.limpiar() }
  }
})

test('Reconsultar invalida la cobertura previa y sus callbacks sin bloquear las otras decisiones por las ofertas', async () => {
  for (const fallo of [false, true]) {
    const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false })
    try {
      const selectAnterior = pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1')
      selectAnterior.props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
      const confirmarAnterior = pagina.botones('Confirmar decisión')[0]
      const pendiente = diferida()
      pagina.control.consultarOfertas = () => pendiente.promesa
      pagina.botones('Actualizar estado')[0].props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, true)
      assert.equal(pagina.renderizar().find((nodo) => nodo.type === 'option' && nodo.props.value === 'CONTINUAR_PARCIAL').props.disabled, true)
      confirmarAnterior.props.onClick()
      assert.deepEqual(pagina.llamadas.evaluar, [])
      const select = pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1')
      select.props.onChange({ target: { value: 'REABRIR' } })
      assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, false)
      if (fallo) pendiente.rechazar(new ApiError(503, 'Ofertas no disponibles.'))
      else pendiente.resolver([])
      await pagina.asentar()
      selectAnterior.props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
      assert.equal(pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1').props.value, 'REABRIR')
      assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, false)
      if (fallo) assert.ok(pagina.renderizar().some((nodo) => nodo.type === 'p' && /No se pudo verificar la disponibilidad de cobertura parcial/.test(pagina.texto(nodo))))
      pagina.botones('Confirmar decisión')[0].props.onClick()
      await pagina.asentar()
      assert.deepEqual(pagina.llamadas.evaluar, [{ id: 1, datos: { tarea_id: 101, accion: 'REABRIR' } }])
    } finally { pagina.limpiar() }
  }
})

test('Una respuesta de ofertas antigua no habilita cobertura tras una reconsulta o decisión completada', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101, 2: 202 }, puedeSeleccionar: false })
  try {
    const pendiente = diferida()
    pagina.control.consultarOfertas = (id) => id === 1 ? pendiente.promesa : Promise.resolve(pagina.control.ofertas[id])
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    pagina.control.consultarOfertas = async () => []
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    pendiente.resolver(pagina.control.ofertas[1])
    await pagina.asentar()
    assert.deepEqual(pagina.renderizar().filter((nodo) => nodo.type === 'option' && nodo.props.value === 'CONTINUAR_PARCIAL').map((nodo) => nodo.props.disabled), [true, false])
    const otraPendiente = diferida()
    pagina.control.consultarOfertas = () => otraPendiente.promesa
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'REFORMULAR' } })
    pagina.control.tareas[1] = null
    pagina.botones('Confirmar decisión')[0].props.onClick()
    await pagina.asentar()
    otraPendiente.resolver(pagina.control.ofertas[1])
    await pagina.asentar()
    assert.equal(pagina.renderizar().some((nodo) => nodo.props?.id === 'evaluacion-proyecto-1'), false)
    assert.equal(pagina.llamadas.evaluar.length, 1)
  } finally { pagina.limpiar() }
})

test('Salir y volver a Evaluar proyecto descarta las ofertas de la visita anterior', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false })
  try {
    const pendiente = diferida()
    pagina.control.consultarOfertas = () => pendiente.promesa
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    const selectAnterior = pagina.renderizar().find((nodo) => nodo.props?.id === 'evaluacion-proyecto-1')
    pagina.botones('Esperando ofertas')[0].props.onClick()
    await pagina.asentar()
    pagina.control.consultarOfertas = async () => []
    pagina.botones('Esperando Evaluacion')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    pendiente.resolver(pagina.control.ofertas[1])
    await pagina.asentar()
    assert.equal(pagina.renderizar().find((nodo) => nodo.type === 'option' && nodo.props.value === 'CONTINUAR_PARCIAL').props.disabled, true)
    selectAnterior.props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
    pagina.botones('Confirmar decisión')[0].props.onClick()
    assert.deepEqual(pagina.llamadas.evaluar, [])
  } finally { pagina.limpiar() }
})

test('La decisión bloquea su emergencia, descarta doble clic y espera la habilitación real para continuar', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, conMarca: false, puedeSeleccionar: false })
  try {
    const pendiente = diferida()
    pagina.control.evaluar = () => pendiente.promesa
    const select = pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1')
    select.props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
    const decidir = pagina.botones('Confirmar decisión')[0]
    decidir.props.onClick()
    decidir.props.onClick()
    assert.equal(pagina.botones('Confirmar selección').length, 0)
    assert.deepEqual(pagina.llamadas.evaluar, [{ id: 1, datos: { tarea_id: 101, accion: 'CONTINUAR_PARCIAL' } }])
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    assert.deepEqual(pagina.llamadas.confirmar, [])
    assert.equal(pagina.botones('Enviando decisión...')[0].props.disabled, true)
    pagina.control.tareas[1] = null
    pendiente.resolver({ tarea_id: 101 })
    await pagina.asentar()
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /Esperando el siguiente paso/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Esperando Evaluacion')[0].props['aria-current'], 'page')
    decidir.props.onClick()
    assert.equal(pagina.llamadas.evaluar.length, 1)
    pagina.control.ofertas[1].forEach((oferta) => { oferta.puede_seleccionar = true })
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando Evaluacion')[0].props['aria-current'], 'page')
    pagina.control.seleccionLista[1] = true
    pagina.control.emergencias[0].etapa = 'esperando_adjudicacion'
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando adjudicación')[0].props['aria-current'], 'page')
    assert.equal(pagina.botones('Adjudicar').length, 0)
    assert.equal(pagina.botones('Confirmar decisión').length, 0)
    assert.ok(pagina.llamadas.consultarSeleccion.includes(true))
  } finally { pagina.limpiar() }
})

test('Reabrir y reformular observan la transición real de la misma emergencia sin ofertas', async () => {
  for (const [accion, destino, etiqueta] of [['REABRIR', 'esperando_ofertas', 'Esperando ofertas'], ['REFORMULAR', 'esperando_lotes', 'Esperando lotes']]) {
    const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, sinOfertas: true, puedeSeleccionar: false })
    try {
      const select = pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1')
      select.props.onChange({ target: { value: accion } })
      pagina.control.evaluar = async (id, datos) => {
        Object.assign(pagina.control.emergencias.find((item) => item.id === id), { estado: destino, etapa: destino })
        pagina.control.tareas[id] = null
        return { tarea_id: datos.tarea_id }
      }
      pagina.botones('Confirmar decisión')[0].props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      assert.deepEqual(pagina.llamadas.evaluar, [{ id: 1, datos: { tarea_id: 101, accion } }])
      assert.equal(pagina.botones(etiqueta)[0].props['aria-current'], 'page')
      assert.equal(pagina.botones('Confirmar decisión').length, 0)
    } finally { pagina.limpiar() }
  }
})

test('Los rechazos de evaluación requieren reconsulta y un handler antiguo no reenvía la tarea', async () => {
  for (const status of [409, 503]) {
    const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false })
    try {
      pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'REABRIR' } })
      const anterior = pagina.botones('Confirmar decisión')[0]
      pagina.control.evaluar = async () => { throw new ApiError(status, 'Evaluación no disponible.') }
      anterior.props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      assert.equal(pagina.llamadas.evaluar.length, 1)
      assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'Evaluación no disponible.'))
      anterior.props.onClick()
      assert.equal(pagina.llamadas.evaluar.length, 1)
      pagina.control.tareas[1] = 102
      pagina.botones('Actualizar estado')[0].props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      anterior.props.onClick()
      assert.equal(pagina.llamadas.evaluar.length, 1)
      assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, true)
      pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'REFORMULAR' } })
      pagina.control.evaluar = async (id, datos) => ({ tarea_id: datos.tarea_id })
      pagina.botones('Confirmar decisión')[0].props.onClick()
      await pagina.asentar()
      await pagina.asentar()
      assert.equal(pagina.llamadas.evaluar[1].datos.tarea_id, 102)
    } finally { pagina.limpiar() }
  }
})


test('La consulta pendiente bloquea sólo su emergencia y un fallo deja disponible la reconsulta', async () => {
  const pendiente = diferida()
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', conMarca: false, consultaEvaluacion: (id) => id === 1 ? pendiente.promesa : Promise.resolve({ tarea_id: 202 }) })
  try {
    assert.equal(pagina.botones('Confirmar decisión').length, 1)
    assert.equal(pagina.botones('Actualizar estado')[0].props.disabled, true)
    assert.equal(pagina.botones('Actualizar estado').at(-1).props.disabled, false)
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    pendiente.rechazar(new ApiError(503, 'Bonita no disponible.'))
    await pagina.asentar()
    assert.equal(pagina.botones('Actualizar estado')[0].props.disabled, false)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'Bonita no disponible.'))
    pagina.control.consultarEvaluacion = async () => ({ tarea_id: 101 })
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Confirmar decisión').length, 2)
    assert.deepEqual(pagina.llamadas.evaluar, [])
  } finally { pagina.limpiar() }
})

test('Continuar lleva a la adjudicación del municipio sin ofrecer confirmar al coordinador', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, conMarca: false, puedeSeleccionar: false })
  try {
    pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'CONTINUAR_PARCIAL' } })
    pagina.control.evaluar = async (id, datos) => {
      pagina.control.tareas[id] = null
      pagina.control.seleccionLista[id] = true
      pagina.control.emergencias.find((item) => item.id === id).etapa = 'esperando_adjudicacion'
      pagina.control.ofertas[id][0].estado_seleccion = 'seleccionada_para_confirmar'
      pagina.control.ofertas[id][0].adjudicada_en = '2026-11-24T10:00:00Z'
      return { tarea_id: datos.tarea_id }
    }
    pagina.botones('Confirmar decisión')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Esperando adjudicación')[0].props['aria-current'], 'page')
    assert.equal(pagina.botones('Seleccionada para confirmar').length, 1)
    assert.equal(pagina.botones('Confirmar selección').length, 0)
    assert.equal(pagina.botones('Confirmar decisión').length, 0)
  } finally { pagina.limpiar() }
})


test('El municipio adjudica según la elegibilidad de las ofertas', async () => {
  for (const puedeSeleccionar of [true, false]) {
    const pagina = await montarPagina({ componente: 'municipio', conMarca: false, puedeSeleccionar, })
    try {
      assert.equal(pagina.botones('Adjudicar')[0].props.disabled, !puedeSeleccionar)
      pagina.botones('Adjudicar')[0].props.onClick()
      await pagina.asentar()
      assert.deepEqual(pagina.llamadas.adjudicar, puedeSeleccionar ? [{ id: 11, paraSeleccion: true }] : [])
      assert.deepEqual(pagina.llamadas.consultarEvaluacion, [])
    } finally { pagina.limpiar() }
  }
})

test('El municipio confirma ofertas ya seleccionadas sin consultar la evaluación', async () => {
  const pagina = await montarPagina({ componente: 'municipio', puedeSeleccionar: false, })
  try {
    assert.equal(pagina.botones('Confirmar selección')[0].props.disabled, false)
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.confirmar, [1])
    assert.deepEqual(pagina.llamadas.consultarEvaluacion, [])
  } finally { pagina.limpiar() }
})

test('Un GET fallido conserva el bloqueo de una tarea de evaluación conocida y exige reconsultar', async () => {
  const pagina = await montarPagina({ estado: 'esperando_evaluacion', tareas: { 1: 101 }, puedeSeleccionar: false })
  try {
    pagina.renderizar().find((nodo) => nodo.type === 'select' && nodo.props.id === 'evaluacion-proyecto-1').props.onChange({ target: { value: 'REABRIR' } })
    const decisionAnterior = pagina.botones('Confirmar decisión')[0]
    pagina.control.consultarEvaluacion = async () => { throw new ApiError(503, 'Bonita no disponible.') }
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Confirmar decisión')[0]?.props.disabled, true)
    assert.equal(pagina.botones('Adjudicar').length, 0)
    assert.equal(pagina.botones('Confirmar selección').length, 0)
    decisionAnterior.props.onClick()
    assert.deepEqual(pagina.llamadas.evaluar, [])
    assert.deepEqual(pagina.llamadas.adjudicar, [])
    assert.deepEqual(pagina.llamadas.confirmar, [])
    pagina.control.consultarEvaluacion = async (id) => ({ tarea_id: pagina.control.tareas[id] ?? null })
    pagina.botones('Actualizar estado')[0].props.onClick()
    await pagina.asentar()
    await pagina.asentar()
    assert.equal(pagina.botones('Confirmar decisión')[0].props.disabled, false)
    assert.equal(pagina.botones('Adjudicar').length, 0)
  } finally { pagina.limpiar() }
})
