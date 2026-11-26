import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

// Zona fija para que el desplazamiento esperado sea determinista.
process.env.TZ = 'America/Argentina/Buenos_Aires'

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

const prefijoJsx = 'function crearElemento(type, props, ...children){return {type,props:{...props,children}}} function Fragmento({children}){return children}\n'
const moduloHttp = await transpilar('../src/services/http.ts')
const servicios = await import(await transpilar('../src/services/reportes.ts', { './http': moduloHttp }))
const moduloFormato = await transpilar('../src/utils/formato.ts', {
  '../services': urlModulo(`export {ApiError} from ${JSON.stringify(moduloHttp)};`),
})
const moduloMeta = await transpilar('../src/components/MetaIndicador.tsx', { '../utils/formato': moduloFormato }, prefijoJsx)
const reemplazosComponentes = { '../utils/formato': moduloFormato, './MetaIndicador': moduloMeta }
const moduloResumen = await transpilar('../src/components/DashboardEmergencias.tsx', reemplazosComponentes, prefijoJsx)
const moduloReportes = await transpilar('../src/components/ReportesDashboard.tsx', reemplazosComponentes, prefijoJsx)
const moduloComponentes = urlModulo(`export {DashboardEmergencias} from ${JSON.stringify(moduloResumen)};\nexport {ReportesDashboard} from ${JSON.stringify(moduloReportes)};`)

function conFetch(manejador) {
  const fetchOriginal = globalThis.fetch
  const almacenamiento = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'token-prueba' } })
  globalThis.fetch = manejador
  return () => {
    globalThis.fetch = fetchOriginal
    if (almacenamiento) Object.defineProperty(globalThis, 'localStorage', almacenamiento)
    else delete globalThis.localStorage
  }
}

const meta = (alcance = 'filtrado', fuente = 'local') => ({ descripcion: `mide ${fuente}`, fuente, alcance, emergencias_incluidas: [1] })

function tableroDePrueba({ bonitaDisponible = true } = {}) {
  return {
    generado_en: '2026-11-26T12:00:00Z',
    filtros: { desde: null, hasta: null, nivel_gravedad: null },
    resumen: {
      total: { ...meta(), valor: 2 }, abiertas: { ...meta(), valor: 1 }, resueltas: { ...meta(), valor: 1 },
      por_estado_y_gravedad: { ...meta(), filas: [{ estado: 'resuelta', nivel_gravedad: 'alta', cantidad: 1 }] },
      prioridad_promedio_abiertas: { ...meta(), valor: 3.5, n: 1 },
      antiguedad_abiertas_horas: { ...meta(), promedio: 2, n: 1 },
      resolucion_horas: { ...meta('filtrado', 'local+bonita'), promedio: 0.5, n: 1, fuente_fecha: { local: 1, bonita: 0 }, sin_fecha_cierre: [7] },
      evolucion: { ...meta(), filas: [{ fecha: '2026-11-25', aperturas: 2, cierres: 1 }] },
    },
    recursos: {
      por_lote: { ...meta('filtrado', 'local+cloud'), filas: [{ lote_id: 5, emergencia_id: 1, tipo_recurso: 'Agua', tipo_recurso_id: 3, unidad: 'litros', pedido: 10, ofertado: 8, verificado: null, cubierto_confirmado: 8, porcentaje_cobertura: 80 }] },
      totales: { ...meta(), filas: [{ mes: '2026-11', tipo_recurso: 'Agua', tipo_recurso_id: 3, unidad: 'litros', ofertado: 8, verificado: 8, reservado: 8, entregado: 4 }] },
      etiqueta_recursos: 'Recursos entregados',
    },
    proyectos: {
      proyectos: { ...meta(), filas: [{ emergencia_id: 1, zona_afectada: 'Centro', estado: 'resuelta', bonita_case_id: '99', items_totales: 2, items_finalizados: 2, cantidades: [{ tipo_recurso: 'Agua', unidad: 'litros', confirmado: 8, entregado: 4 }], resuelta: true, resolucion_horas: 0.5 }] },
      consorcios: { ...meta(), emergencias_resueltas: 4, resueltas_con_consorcio: 1, porcentaje: 25 },
      ranking_ongs: { ...meta('global'), filas: [{ organizacion_id: 1, organizacion_nombre: 'ONG Uno', tipo_recurso: 'Agua', unidad: 'litros', cantidad_confirmada: 8 }] },
    },
    bonita: {
      ...meta('filtrado', 'bonita'), disponible: bonitaDisponible, error: bonitaDisponible ? null : 'tiempo de espera agotado',
      casos_activos: 1, casos_finalizados: 2, casos_cancelados: 1, casos_camino_alternativo: 0,
      tiempos_por_etapa: [{ etapa: 'Evaluar proyecto', promedio_horas: 1, n: 3 }],
      verificacion: [{ emergencia_id: 1, bonita_case_id: '99', estado_local: 'resuelta', estado_bonita: 'completed', resolucion_horas: 0.5 }],
    },
  }
}

async function montarPagina({ tablero = tableroDePrueba(), fallarTablero = false } = {}) {
  const estados = [], memos = [], efectos = [], dependencias = [], limpiezas = []
  let indiceEstado = 0, indiceMemo = 0, indiceEfecto = 0
  const llamadas = { tablero: [] }
  const cambiaron = (anteriores, deps) => !anteriores || deps.some((valor, indice) => valor !== anteriores[indice])
  const control = {
    async obtenerTablero(filtros) {
      llamadas.tablero.push(filtros)
      if (fallarTablero) throw new Error('falló')
      return structuredClone(tablero)
    },
    async exportarReporteCompleto() { throw new Error('no se usa') },
    useState(inicial) {
      const indice = indiceEstado++
      if (!(indice in estados)) estados[indice] = typeof inicial === 'function' ? inicial() : inicial
      return [estados[indice], (valor) => { estados[indice] = typeof valor === 'function' ? valor(estados[indice]) : valor }]
    },
    useMemo(fabrica, deps) {
      const indice = indiceMemo++
      if (cambiaron(memos[indice]?.deps, deps)) memos[indice] = { valor: fabrica(), deps }
      return memos[indice].valor
    },
    useEffect(efecto, deps) {
      const indice = indiceEfecto++
      if (cambiaron(dependencias[indice], deps)) {
        dependencias[indice] = deps
        efectos.push(() => { limpiezas[indice]?.(); limpiezas[indice] = efecto() })
      }
    },
  }
  const clave = `__dashboard_${Math.random().toString(36).slice(2)}`
  globalThis[clave] = control
  const acceso = `globalThis[${JSON.stringify(clave)}]`
  const exportar = (nombres) => nombres.map((nombre) => `export const ${nombre}=(...args)=>${acceso}.${nombre}(...args);`).join('\n')
  const moduloPagina = await transpilar('../src/pages/DashboardEmergenciasPage.tsx', {
    react: urlModulo(exportar(['useState', 'useMemo', 'useEffect'])),
    '../services': urlModulo(exportar(['obtenerTablero', 'exportarReporteCompleto'])),
    '../components': moduloComponentes,
    '../utils/formato': moduloFormato,
  }, prefijoJsx)
  const { DashboardEmergenciasPage } = await import(moduloPagina)
  function aplanar(nodo) {
    if (nodo == null || typeof nodo === 'boolean') return []
    if (Array.isArray(nodo)) return nodo.flatMap(aplanar)
    if (typeof nodo !== 'object') return [nodo]
    if (typeof nodo.type === 'function') return aplanar(nodo.type(nodo.props))
    return [nodo, ...aplanar(nodo.props.children)]
  }
  function renderizar() {
    indiceEstado = 0; indiceMemo = 0; indiceEfecto = 0
    return aplanar(DashboardEmergenciasPage())
  }
  const textoPlano = () => renderizar().filter((valor) => typeof valor !== 'object').join('')
  async function asentar() {
    for (let vuelta = 0; vuelta < 3; vuelta++) {
      renderizar()
      for (const efecto of efectos.splice(0)) efecto()
      await new Promise((resolve) => setImmediate(resolve))
    }
  }
  await asentar()
  return { llamadas, renderizar, textoPlano, asentar, limpiar: () => { for (const limpiar of limpiezas) limpiar?.(); delete globalThis[clave] } }
}

test('La consulta del tablero envía las fechas con la zona del navegador y "Hasta" inclusivo', async () => {
  const urls = []
  const restaurar = conFetch(async (url) => { urls.push(url); return new Response(JSON.stringify(tableroDePrueba())) })
  try {
    await servicios.obtenerTablero({ desde: '2026-11-01', hasta: '2026-11-26', nivel_gravedad: 'alta' })
    await servicios.obtenerTablero({})
    process.env.TZ = 'Asia/Kolkata'
    await servicios.obtenerTablero({ desde: '2026-11-01', hasta: '2026-11-26' })
  } finally {
    process.env.TZ = 'America/Argentina/Buenos_Aires'
    restaurar()
  }
  const [conFiltros, sinFiltros, otraZona] = urls.map((url) => new URL(url))
  assert.equal(conFiltros.pathname, '/api/v1/reportes/tablero')
  assert.equal(conFiltros.searchParams.get('desde'), '2026-11-01T00:00:00-03:00')
  assert.equal(conFiltros.searchParams.get('hasta'), '2026-11-26T23:59:59.999-03:00')
  assert.equal(conFiltros.searchParams.get('nivel_gravedad'), 'alta')
  assert.equal(sinFiltros.search, '')
  assert.equal(otraZona.searchParams.get('desde'), '2026-11-01T00:00:00+05:30')
  assert.equal(otraZona.searchParams.get('hasta'), '2026-11-26T23:59:59.999+05:30')
})

test('La exportación usa los mismos filtros con zona horaria', async () => {
  const urls = []
  const restaurar = conFetch(async (url) => { urls.push(url); return new Response('a,b') })
  try {
    await servicios.exportarReporteCompleto({ desde: '2026-11-26', hasta: '2026-11-26' }, 'csv')
  } finally {
    restaurar()
  }
  const url = new URL(urls[0])
  assert.equal(url.pathname, '/api/v1/reportes/exportar')
  assert.equal(url.searchParams.get('desde'), '2026-11-26T00:00:00-03:00')
  assert.equal(url.searchParams.get('hasta'), '2026-11-26T23:59:59.999-03:00')
  assert.equal(url.searchParams.get('formato'), 'csv')
})

test('La página hace una sola llamada al tablero por carga y muestra los paneles', async () => {
  const pagina = await montarPagina()
  try {
    assert.equal(pagina.llamadas.tablero.length, 1)
    assert.deepEqual(pagina.llamadas.tablero[0], {})
    const texto = pagina.textoPlano()
    for (const esperado of ['Antigüedad promedio de abiertas', 'Tiempo de resolución de finalizadas', '1 resuelta sin fecha de cierre (#7)',
      'Aperturas', 'Cierres', 'Cobertura por lote', 'Recursos entregados', 'Proyectos y avance', 'Ranking de ONG',
      'Casos finalizados', 'Casos cancelados', 'Global', 'Local + Sistema Nacional']) {
      assert.ok(texto.includes(esperado), `Falta "${esperado}"`)
    }
    await pagina.asentar()
    assert.equal(pagina.llamadas.tablero.length, 1)
  } finally {
    pagina.limpiar()
  }
})

test('Con Bonita no disponible se muestra el aviso y el resto del tablero renderiza', async () => {
  const pagina = await montarPagina({ tablero: tableroDePrueba({ bonitaDisponible: false }) })
  try {
    const texto = pagina.textoPlano()
    assert.ok(texto.includes('Bonita no disponible: tiempo de espera agotado'))
    assert.ok(!texto.includes('Casos finalizados'))
    for (const esperado of ['Emergencias totales', 'Cobertura por lote', 'Proyectos y avance', 'Consorcios']) {
      assert.ok(texto.includes(esperado), `Falta "${esperado}"`)
    }
  } finally {
    pagina.limpiar()
  }
})

test('Un error de carga se informa en el tablero', async () => {
  const pagina = await montarPagina({ fallarTablero: true })
  try {
    assert.equal(pagina.llamadas.tablero.length, 1)
    assert.ok(pagina.textoPlano().includes('No se pudo cargar el dashboard.'))
  } finally {
    pagina.limpiar()
  }
})
