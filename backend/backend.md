# backend.md — Guía del Subagente BACKEND

> **Entorno:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL 16 + Bonita BPM.
> **Idioma:** Todo el código, nombres y comentarios se escriben en **español**.
> **Regla de oro:** Leé este archivo completo antes de tocar cualquier código.

---

## 1. Principio de Alcance Mínimo

- Implementá **estricta y únicamente** lo solicitado en la tarea delegada.
- Si se te pide un endpoint, creá la ruta y el handler exacto. Si el service o modelo no existen, generá únicamente el stub/mock mínimo necesario para que el código sea sintácticamente válido y ejecutable sin inventar estructuras de datos innecesarias.
- No modifiques tablas de base de datos ni relaciones existentes salvo que la tarea lo exija expresamente.

---

## 2. Arquitectura de Capas (`backend/app/`)
backend/app/ 
├── api/routes/   # CONTROLLERS FINOS: Validación de contratos y delegación al service.
├── dto/          # DTOs por caso de uso: contrato de salida backend→frontend; los carga el service.
├── services/     # LÓGICA DE NEGOCIO: Transacciones, queries DB y lógica de dominio.
├── schemas/      # CONTRATOS PYDANTIC de entrada (Base, Create, Update).
├── models/       # ENTIDADES SQLALCHEMY: Tablas con Mapped[] y mapped_column().
└── integrations/ # EXTERNOS: Clientes HTTP puros (Bonita BPM).

### Reglas de Capas
1. **Controllers (`api/routes/`):** No contienen queries SQL ni lógica de negocio. Reciben parámetros, llaman a `services/` y tipan con `schemas/`.
2. **Servicios (`services/`):** Reciben `db: Session`. Lanzan `HTTPException` (404, 400, 409, 503).
3. **Modelos (`models/`):** Todo modelo nuevo debe re-exportarse en `models/__init__.py`.
4. **Registro de Rutas:** Nuevos routers deben incluirse en `app/main.py` bajo el prefijo `API_PREFIX = "/api/v1"`.

---

## 3. Comandos de Verificación Obligatorios

Antes de reportar tu tarea como finalizada, ejecutá en `backend/`:

```bash
python -c "from app.main import app; print('App importada con éxito')"
```

Si hay tests unitarios configurados en el proyecto, ejecutá:
```bash
pytest
```

---

## 4. Formato de Reporte de Cierre

Al finalizar, devolvé al orquestador este formato sin texto superfluo:

- Archivos modificados/creados: (lista de rutas)
- Contratos expuestos: (Verbo HTTP + Path + Schema Entrada/Salida si aplica)
- Resultado de verificación: Importación de app (OK)