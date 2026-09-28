# frontend.md — Guía del Subagente FRONTEND

> **Entorno:** React 19 + TypeScript + Vite + Bun + Tailwind CSS v4.
> **Idioma:** Todo el código, nombres y comentarios se escriben en **español**.
> **Regla de oro:** Leé este archivo completo antes de tocar cualquier código.

---

## 1. Principio de Alcance Mínimo

- Implementá **estricta y únicamente** lo solicitado en la tarea delegada.
- No agregues librerías adicionales, utilitarios no pedidos, ni refactorices pantallas vecinas.
- No inventes endpoints; consumí únicamente los definidos en `types/` y `services/` acordes a `backend/backend.md`.

---

## 2. Arquitectura de Capas (`frontend/src/`)
src/
├── pages/       # VISTAS: Estado de UI local y layouts. Prohibido llamar a fetch/http acá.
├── services/    # COMUNICACIÓN: Clientes HTTP por dominio usando http.ts. Sin hooks de React.
├── types/       # CONTRATOS: DTOs / Interfaces TypeScript. Espejo de los DTOs del backend.
└── index.css    # Estilos globales (Tailwind v4).

### Reglas de Capas
1. **Páginas (`pages/`):** Solo consumen servicios importados desde `../services`. Manejan errores vía captura de `ApiError`. Exportadas como *named export* y re-exportadas en `pages/index.ts`.
2. **Servicios (`services/`):** Un archivo por dominio (`services/<dominio>.ts`). Consumen `http.ts` y usan el prefijo `/api/v1`. Re-exportados en `services/index.ts`.
3. **Contratos (`types/`):** Interfaces sin lógica (`types/<dominio>.ts`). Re-exportados en `types/index.ts`.
4. **Barrels obligatorios:** Siempre importar desde `../services` y `../types`. Mantener `index.ts` actualizado.

---

## 3. Comandos de Verificación Obligatorios

Antes de reportar tu tarea como finalizada, ejecutá en `frontend/`:

```bash
bun run lint
bun run build
Ambos deben finalizar con código de salida 0. Si fallan, corregí los tipos o sintaxis antes de responder.
```

---

## 4. Formato de Reporte de Cierre
Al finalizar, devolvé al orquestador este formato sin texto superfluo:

- Archivos modificados/creados: (lista de rutas)
- Alcance cubierto: (resumen de 1-2 líneas de lo implementado)
- Resultado de verificación: bun run lint (OK) / bun run build (OK)