import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

async function compilarServicio(nombre) {
  const fuente = await readFile(new URL(`../src/services/${nombre}.ts`, import.meta.url), 'utf8')
  return ts.transpileModule(fuente, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  }).outputText
}

const moduloHttp = `data:text/javascript;base64,${Buffer.from(await compilarServicio('http')).toString('base64')}`
const codigoRol = (await compilarServicio('rol')).replace("'./http'", JSON.stringify(moduloHttp))
const moduloRol = `data:text/javascript;base64,${Buffer.from(codigoRol).toString('base64')}`
const codigoAuth = (await compilarServicio('auth'))
  .replace("'./http'", JSON.stringify(moduloHttp))
  .replace("'./rol'", JSON.stringify(moduloRol))
const { iniciarSesion, registrar, cerrarSesion, restaurarSesion } = await import(
  `data:text/javascript;base64,${Buffer.from(codigoAuth).toString('base64')}`
)
const { apiGet, ApiError } = await import(moduloHttp)

test('Login autentica las consultas; crear usuario conserva el token y logout lo elimina', async () => {
  const fetchOriginal = globalThis.fetch
  const almacenamientoOriginal = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  const almacenamiento = new Map()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (clave) => almacenamiento.get(clave) ?? null,
      setItem: (clave, valor) => almacenamiento.set(clave, valor),
      removeItem: (clave) => almacenamiento.delete(clave),
    },
  })
  const peticiones = []
  globalThis.fetch = async (url, opciones) => {
    peticiones.push({ url, opciones })
    if (url.endsWith('/auth/me')) return new Response(JSON.stringify({ id: 1, rol_id: 2 }))
    if (url.endsWith('/roles')) return new Response(JSON.stringify([{ id: 2, nombre: 'centro_coordinador' }]))
    return new Response(JSON.stringify({
      access_token: url.endsWith('/auth/login') ? 'token-coordinador' : 'token-nuevo-usuario',
    }), { status: 200 })
  }
  try {
    await iniciarSesion({ email: 'coordinador@ejemplo.com', password: 'secreto' })
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, undefined)
    await apiGet('/emergencias')
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, 'Bearer token-coordinador')
    assert.equal((await restaurarSesion()).rol, 'centro_coordinador')
    assert.ok(peticiones.at(-1).url.endsWith('/roles'))
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, 'Bearer token-coordinador')
    await registrar({ nombre: 'Ana', apellido: 'Gomez', rol_id: 3, organizacion_id: 2 })
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, 'Bearer token-coordinador')
    assert.equal(JSON.parse(peticiones.at(-1).opciones.body).organizacion_id, 2)
    await apiGet('/organizaciones')
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, 'Bearer token-coordinador')
    cerrarSesion()
    await apiGet('/emergencias')
    assert.equal(peticiones.at(-1).opciones.headers.Authorization, undefined)
    for (const estado of [401, 403]) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Acceso rechazado' }), { status: estado })
      await assert.rejects(apiGet('/emergencias'), (error) =>
        error instanceof ApiError && error.status === estado && error.detail === 'Acceso rechazado')
    }
  } finally {
    cerrarSesion()
    globalThis.fetch = fetchOriginal
    if (almacenamientoOriginal) Object.defineProperty(globalThis, 'localStorage', almacenamientoOriginal)
    else delete globalThis.localStorage
  }
})
