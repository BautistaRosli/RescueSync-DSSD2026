import { useState } from 'react'
import { ConvocatoriasPage } from './ConvocatoriasPage'
import { InventarioPage } from './InventarioPage'
import { MisOfertasPage } from './MisOfertasPage'
import { claseAviso, claseCard, claseSubtitulo, claseTitulo, clasePestania } from '../ui/clases'
import type { AuthResponse } from '../types'

type VistaOng = 'convocatorias' | 'ofertas' | 'inventario'

const PESTANIAS_ONG: { valor: VistaOng; etiqueta: string }[] = [
  { valor: 'convocatorias', etiqueta: 'Convocatorias' },
  { valor: 'ofertas', etiqueta: 'Mis ofertas' },
  { valor: 'inventario', etiqueta: 'Inventario' },
]

export function PanelOngPage({ sesion }: { sesion: AuthResponse }) {
  const [vista, setVista] = useState<VistaOng>('convocatorias')

  const organizacionId = sesion.usuario.organizacion_id

  if (organizacionId === null) {
    return (
      <section className={claseCard}>
        <h2 className={claseTitulo}>Falta asociar tu organización</h2>
        <p className={`${claseSubtitulo} mb-5`}>
          Tu usuario tiene rol de representante de ONG pero no está vinculado a
          ninguna organización, así que todavía no podés postular recursos.
        </p>
        <p className={claseAviso}>
          Registrate de nuevo eligiendo tu ONG en el formulario de alta, o pedile
          al administrador que asocie tu usuario a una organización.
        </p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-6">
      <nav aria-label="Secciones de la ONG" className="flex flex-wrap gap-2">
        {PESTANIAS_ONG.map((pestania) => (
          <button
            key={pestania.valor}
            type="button"
            aria-current={vista === pestania.valor ? 'page' : undefined}
            onClick={() => setVista(pestania.valor)}
            className={clasePestania(vista === pestania.valor)}
          >
            {pestania.etiqueta}
          </button>
        ))}
      </nav>

      {vista === 'convocatorias' && (
        <ConvocatoriasPage organizacionId={organizacionId} />
      )}
      {vista === 'ofertas' && <MisOfertasPage organizacionId={organizacionId} />}
      {vista === 'inventario' && (
        <InventarioPage organizacionId={organizacionId} />
      )}
    </section>
  )
}
