import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

async function importarModulo(ruta, reemplazos = {}) {
  const fuente = await readFile(new URL(ruta, import.meta.url), 'utf8')
  let codigo = ts.transpileModule(fuente, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  }).outputText
  for (const [origen, destino] of Object.entries(reemplazos)) {
    codigo = codigo.replace(JSON.stringify(origen), JSON.stringify(destino))
      .replace(`'${origen}'`, JSON.stringify(destino))
  }
  return `data:text/javascript;base64,${Buffer.from(codigo).toString('base64')}`
}

const formulario = await import(await importarModulo('../src/pages/formularioLote.ts'))
const borradorValido = {
  tipo: ' Botiquín táctico ',
  cantidad: '5',
  unidad: ' unidades ',
  descripcion: ' Primera respuesta ',
  tipo_recurso_id: '10',
}

test('El borrador genera un ID nacional numérico sin cambiar los demás datos', () => {
  const validacion = formulario.validarBorradorLote(borradorValido)
  assert.equal(validacion.error, null)
  assert.deepEqual(validacion.datos, {
    tipo: 'Botiquín táctico', cantidad: 5, unidad: 'unidades',
    descripcion: 'Primera respuesta', tipo_recurso_id: 10,
  })
})

test('El borrador rechaza un ID nacional que no sea entero positivo', () => {
  for (const tipo_recurso_id of ['', ' ', '0', '-1', '1.5', 'texto', 'Infinity']) {
    const resultado = formulario.validarBorradorLote({ ...borradorValido, tipo_recurso_id })
    assert.equal(resultado.datos, null, `Se aceptó el ID ${JSON.stringify(tipo_recurso_id)}`)
    assert.match(resultado.error, /ID.*entero mayor a 0/)
  }
})

test('La edición precarga la equivalencia nacional y deja vacíos los lotes antiguos', () => {
  const lote = {
    id: 99, emergencia_id: 1, tipo: 'Botiquín táctico', cantidad: 5,
    unidad: 'unidades', descripcion: 'Primera respuesta', tipo_recurso_id: 10,
  }
  assert.deepEqual(formulario.borradorDesdeLote(lote), {
    tipo: lote.tipo, cantidad: '5', unidad: lote.unidad,
    descripcion: lote.descripcion, tipo_recurso_id: '10',
  })
  for (const tipo_recurso_id of [null, undefined, 0]) {
    assert.equal(formulario.borradorDesdeLote({ ...lote, tipo_recurso_id }).tipo_recurso_id, '')
  }
})

test('Cambiar tipo o unidad exige reindicar el ID y permite confirmar el mismo número', () => {
  for (const [campo, valor] of [['tipo', 'Agua'], ['unidad', 'cajas']]) {
    const cambiado = formulario.cambiarCampoBorradorLote(borradorValido, campo, valor)
    assert.equal(cambiado.tipo_recurso_id, '')
    assert.equal(formulario.validarBorradorLote(cambiado).datos, null)
    const confirmado = formulario.cambiarCampoBorradorLote(cambiado, 'tipo_recurso_id', '10')
    assert.equal(formulario.validarBorradorLote(confirmado).datos.tipo_recurso_id, 10)
  }
  for (const [campo, valor] of [
    ['cantidad', '9'], ['descripcion', 'Otro detalle'],
    ['tipo', 'Botiquín táctico'], ['unidad', 'unidades'],
  ]) {
    const cambiado = formulario.cambiarCampoBorradorLote(borradorValido, campo, valor)
    assert.equal(cambiado.tipo_recurso_id, '10')
    assert.equal(cambiado[campo], valor)
  }
})

test('POST y PATCH serializan el ID validado como entero en los servicios existentes', async () => {
  const moduloHttp = await importarModulo('../src/services/http.ts')
  const servicios = await import(await importarModulo('../src/services/emergencia.ts', { './http': moduloHttp }))
  const peticiones = []
  const fetchOriginal = globalThis.fetch
  const almacenamientoOriginal = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true, value: { getItem: () => null },
  })
  globalThis.fetch = async (url, opciones) => {
    const cuerpo = JSON.parse(opciones.body)
    peticiones.push({ url, metodo: opciones.method, cuerpo })
    return new Response(JSON.stringify({ id: 99, emergencia_id: 1, ...cuerpo }), { status: 200 })
  }
  try {
    const { datos } = formulario.validarBorradorLote(borradorValido)
    const creado = await servicios.crearLote(1, datos)
    const actualizado = await servicios.actualizarLote(99, datos)
    assert.deepEqual(peticiones.map(({ url, metodo }) => ({ url, metodo })), [
      { url: 'http://localhost:8000/api/v1/emergencias/1/lotes', metodo: 'POST' },
      { url: 'http://localhost:8000/api/v1/lotes/99', metodo: 'PATCH' },
    ])
    for (const { cuerpo } of peticiones) {
      assert.equal(cuerpo.tipo_recurso_id, 10)
      assert.equal(cuerpo.cantidad, 5)
      assert.equal(cuerpo.tipo, 'Botiquín táctico')
    }
    assert.equal(creado.tipo_recurso_id, 10)
    assert.equal(actualizado.tipo_recurso_id, 10)
  } finally {
    globalThis.fetch = fetchOriginal
    if (almacenamientoOriginal) {
      Object.defineProperty(globalThis, 'localStorage', almacenamientoOriginal)
    } else {
      delete globalThis.localStorage
    }
  }
})
