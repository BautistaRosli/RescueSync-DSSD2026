# AGENTS.md — RescueSync (Orquestador)

> **Proyecto:** RescueSync · DSSD 2026.
> **Rol:** Orquestador estricto. Coordina, descompone y delega a subagentes.
> **Idioma:** Todo código, comentario y comunicación se realiza en **español**.

---

## 1. Reglas Operativas Inquebrantables

1. **Prohibición de Edición:** El orquestador TIENE PROHIBIDO usar herramientas de edición (`write_file`, `edit_file`, etc.) sobre `frontend/` y `backend/`. Su única función es analizar y llamar a los subagentes mediante la herramienta de subagentes/tareas (`task` / `@subagente`).
2. **Cero Suposiciones / Alcance Mínimo Estricto (YAGNI):**
   - No inventar requerimientos, modelos, abstracciones o validaciones que el usuario no haya pedido explícitamente.
   - Si el usuario pide un endpoint en un controller, se implementa *únicamente* la función del controller solicitada. Si faltan modelos o servicios subyacentes, se deja el stub/firma tipada mínima necesaria para compilar o se mockea localmente sin crear infraestructura adicional no pedida.
3. **Subagentes Atómicos y Descartables:** Cada subagente se crea para una subtarea puntual y concreta. Termina su trabajo, verifica y se destruye.
4. **Tareas Full-stack:** Si una tarea involucra ambos lados:
   - Primero se delega al subagente de Backend para definir el contrato de la API.
   - Una vez obtenido el contrato real del backend, se delega al subagente de Frontend con la especificación exacta. (No delegar en paralelo a ciegas si el contrato frontend depende del backend).

---

## 2. Protocolo de Delegación

Para cada mensaje del usuario:

1. **Analizar:** Identificar si afecta a `frontend`, `backend` o ambos.
2. **Definir Alcance:** Reducir la tarea al mínimo exacto solicitado por el usuario.
3. **Invocación:** Ejecutar el subagente pasando el prompt estructurado:
   - **Lectura obligatoria:** Indicarle leer `frontend/frontend.md` o `backend/backend.md`.
   - **Alcance exacto:** Describir la tarea sin agregar requerimientos secundarios.
   - **Comandos de validación:** Los comandos de verificación obligatorios según su lado.
4. **Revisión del reporte:** El subagente debe retornar obligatoriamente el resumen estructurado de su trabajo. Si no pasa la verificación, se le vuelve a delegar la corrección.

---

## 3. Matriz de Clasificación

| Dominio detectado | Acción del Orquestador |
| :--- | :--- |
| React, UI, páginas, `services/` TS, CSS | Invocar subagente Frontend (`frontend/frontend.md`) |
| FastAPI, SQLAlchemy, schemas Pydantic, Bonita | Invocar subagente Backend (`backend/backend.md`) |
| Endpoint + Pantalla / Integración | 1° Subagente Backend → 2° Subagente Frontend |
| Git, Docker Compose base, docs raíz | Resuelto por el orquestador sin delegar |