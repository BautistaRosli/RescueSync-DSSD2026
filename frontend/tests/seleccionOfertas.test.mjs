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
      jsx: ts.JsxEmit.React, jsxFactory: 'crearElemento',
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

async function montarPagina() {
  const estados = [], referencias = [], efectos = [], dependencias = []
  let indiceEstado = 0, indiceRef = 0, indiceEfecto = 0
  const oferta = (id, emergencia_id, adjudicada_en = null) => ({
    id, emergencia_id, adjudicada_en, organizacion_id: id, organizaciones: [],
    fecha_hora_oferta: '2026-11-21T10:00:00Z', items: [{ id, lote_necesidad_id: id }],
  })
  const emergencias = [1, 2].map((id) => ({
    id, nombre: `Emergencia ${id}`, descripcion: '', ubicacion: '', gravedad: 'baja',
    nivel_gravedad: 'baja', estado: 'esperando_ofertas', publicada: true,
    fecha_hora: null, fecha_publicacion: null, lotes: [],
  }))
  const ofertas = {
    1: [oferta(11, 1, '2026-11-20T10:00:00Z'), oferta(12, 1), oferta(13, 1)],
    2: [oferta(21, 2)],
  }
  const llamadas = { adjudicar: [], confirmar: [] }
  const control = {
    adjudicar: async (id) => ({ oferta_id: id, mensaje: 'Correo enviado.' }),
    confirmar: async (id) => ({ emergencia_id: id, cantidad_pares: 2, ya_confirmada: false }),
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
    useEffect(efecto, deps) {
      const indice = indiceEfecto++
      if (!dependencias[indice] || deps.some((valor, i) => valor !== dependencias[indice][i])) {
        dependencias[indice] = deps
        efectos.push(efecto)
      }
    },
    async listarBandejaEmergencias() {
      return { items: emergencias, paginas: 1, pagina: 1, total: 2 }
    },
    async listarOfertasDeEmergencia(id) { return ofertas[id] },
    adjudicarOferta(id) { llamadas.adjudicar.push(id); return control.adjudicar(id) },
    confirmarSeleccionOfertas(id) { llamadas.confirmar.push(id); return control.confirmar(id) },
  }
  const clave = `__seleccion_${Math.random().toString(36).slice(2)}`
  globalThis[clave] = control
  const acceso = `globalThis[${JSON.stringify(clave)}]`
  const hooks = urlModulo(['useState', 'useRef', 'useEffect'].map((nombre) =>
    `export const ${nombre}=(...args)=>${acceso}.${nombre}(...args);`).join('\n'))
  const nombresServicios = [
    'actualizarLote', 'adjudicarOferta', 'confirmarSeleccionOfertas', 'crearLote',
    'eliminarLote', 'listarBandejaEmergencias', 'listarOfertasDeEmergencia', 'publicarEmergencia',
  ]
  const moduloServicios = urlModulo(`export {ApiError} from ${JSON.stringify(moduloHttp)};\n` +
    nombresServicios.map((nombre) =>
      `export const ${nombre}=(...args)=>${acceso}.${nombre}(...args);`).join('\n'))
  const moduloPagina = await transpilar('../src/pages/CentroCoordinadorPage.tsx', {
    react: hooks, '../services': moduloServicios,
    './formularioLote': await transpilar('../src/pages/formularioLote.ts'),
    '../ui/clases': await transpilar('../src/ui/clases.ts'),
  }, 'function crearElemento(type, props, ...children){return {type,props:{...props,children}}}\n')
  const { CentroCoordinadorPage } = await import(moduloPagina)
  function aplanar(nodo) {
    if (nodo == null || typeof nodo === 'boolean') return []
    if (Array.isArray(nodo)) return nodo.flatMap(aplanar)
    if (typeof nodo !== 'object') return [nodo]
    if (typeof nodo.type === 'function') return aplanar(nodo.type(nodo.props))
    return [nodo, ...aplanar(nodo.props.children)]
  }
  function renderizar() {
    indiceEstado = 0; indiceRef = 0; indiceEfecto = 0
    return aplanar(CentroCoordinadorPage())
  }
  const texto = (nodo) => aplanar(nodo.props.children).filter((valor) => typeof valor !== 'object').join('')
  const botones = (etiqueta) => renderizar().filter((nodo) => nodo.type === 'button' && texto(nodo) === etiqueta)
  async function asentar() {
    renderizar()
    for (const efecto of efectos.splice(0)) efecto()
    await new Promise((resolve) => setImmediate(resolve))
  }
  await asentar()
  botones('Publicadas')[0].props.onClick()
  await asentar()
  const filas = renderizar().filter((nodo) => nodo.type === 'button' && nodo.props['aria-expanded'] === false)
  for (const fila of filas) fila.props.onClick()
  await asentar()
  return { control, llamadas, botones, renderizar, texto, asentar, limpiar: () => delete globalThis[clave] }
}

test('La selección bloquea duplicados, respeta adjudicaciones persistidas y permite reintentar por emergencia', async () => {
  const pagina = await montarPagina()
  try {
    assert.equal(pagina.botones('Confirmar selección').length, 2)
    assert.equal(pagina.botones('Adjudicada').length, 1)
    pagina.botones('Adjudicada')[0].props.onClick()
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
    assert.deepEqual(pagina.llamadas.adjudicar, [12])
    assert.deepEqual(pagina.llamadas.confirmar, [])
    assert.equal(pagina.botones('Confirmar selección')[0].props.disabled, true)
    pendiente.resolver({ oferta_id: 12, mensaje: 'Correo enviado.' })
    await pagina.asentar()
    assert.equal(pagina.botones('Adjudicada').length, 2)
    adjudicar.props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [12])
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
    assert.deepEqual(pagina.llamadas.adjudicar, [12])
    confirmacion.rechazar(new ApiError(503, 'Bonita no disponible.'))
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'Bonita no disponible.'))
    pagina.control.confirmar = async (id) => ({ emergencia_id: id, cantidad_pares: 2, ya_confirmada: true })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    assert.deepEqual(pagina.llamadas.confirmar, [1, 1])
    assert.equal(pagina.botones('Selección confirmada')[0].props.disabled, true)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /ya estaba confirmada/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Confirmar selección').length, 1)
    assert.equal(pagina.botones('Adjudicar')[0].props.disabled, true)
    pagina.botones('Adjudicar')[0].props.onClick()
    confirmar.props.onClick()
    assert.deepEqual(pagina.llamadas.adjudicar, [12])
    assert.deepEqual(pagina.llamadas.confirmar, [1, 1])
  } finally { pagina.limpiar() }
})

test('Una adjudicación rechazada no marca la oferta y una respuesta de otra selección no anuncia éxito', async () => {
  const pagina = await montarPagina()
  try {
    pagina.control.adjudicar = async () => { throw new ApiError(409, 'No se pudo adjudicar.') }
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Adjudicada').length, 1)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && pagina.texto(nodo) === 'No se pudo adjudicar.'))
    pagina.control.adjudicar = async () => ({ oferta_id: 99, mensaje: 'Correo enviado.' })
    pagina.botones('Adjudicar')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Adjudicada').length, 1)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && /respuesta de adjudicación/.test(pagina.texto(nodo))))
    pagina.control.confirmar = async () => ({ emergencia_id: 99, cantidad_pares: 2, ya_confirmada: false })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    assert.equal(pagina.botones('Selección confirmada').length, 0)
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'alert' && /respuesta/.test(pagina.texto(nodo))))
    pagina.control.confirmar = async (id) => ({ emergencia_id: id, cantidad_pares: 1, ya_confirmada: false })
    pagina.botones('Confirmar selección')[0].props.onClick()
    await pagina.asentar()
    assert.ok(pagina.renderizar().some((nodo) => nodo.props?.role === 'status' && /Selección confirmada correctamente/.test(pagina.texto(nodo))))
    assert.equal(pagina.botones('Adjudicar')[0].props.disabled, true)
    assert.equal(pagina.botones('Adjudicar')[2].props.disabled, false)
  } finally { pagina.limpiar() }
})
