# backend.md — Guía del Subagente BACKEND

> **Entorno:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL 16 + Bonita BPM.
> **Idioma:** Todo el código, nombres y comentarios se escriben en **español**.
> **Arquitectura:** Monolito modular organizado por **dominios**, con **arquitectura en capas** dentro de cada dominio.
> **Regla de oro:** Leé este archivo completo antes de tocar cualquier código.

---

## 1. Principio de Alcance Mínimo

- Implementá **estricta y únicamente** lo solicitado en la tarea delegada.
- Si se te pide un endpoint, creá la ruta y los componentes necesarios dentro del dominio correspondiente.
- Si el service, repository, modelo o schema todavía no existen, generá únicamente lo mínimo necesario para implementar la tarea. **No inventes entidades, relaciones, endpoints o estructuras de datos que la tarea no requiera.**
- No modifiques tablas de base de datos ni relaciones existentes salvo que la tarea lo exija expresamente.
- No conviertas el proyecto en microservicios. El backend web es un **monolito modular**.
- No mezcles responsabilidades entre dominios sin una razón de negocio clara.

---

## 2. Arquitectura General: Dominios + Capas

El backend debe seguir un modelo de **organización por dominios (feature/domain oriented)** y una **arquitectura en capas**.

La idea principal es:

```text
backend/app/
│
├── api/
│   └── routes/                  # Capa HTTP / Controllers finos
│
├── domains/                     # Dominios funcionales del sistema
│   ├── usuarios/
│   ├── emergencias/
│   ├── lotes/
│   ├── ofertas/
│   ├── consorcios/
│   ├── inventario/
│   ├── notificaciones/
│   └── dashboard/
│
├── integrations/                # Sistemas externos
│   └── bonita/
│
├── database/                    # Infraestructura de persistencia
│
└── main.py
```

No todos los dominios tienen que existir desde el comienzo. **Crealos únicamente cuando sean necesarios para una tarea concreta.**

Cada dominio debe encapsular sus propias reglas, modelos, schemas, repositories y services cuando corresponda.

### Estructura interna de un dominio

Cuando un dominio tenga suficiente complejidad, su estructura será:

```text
domains/
└── ofertas/
    ├── models.py
    ├── schemas.py
    ├── repository.py
    └── service.py
```

Para dominios simples, no es obligatorio crear archivos que todavía no sean necesarios.

### Ejemplo conceptual

```text
domains/
├── emergencias/
│   ├── models.py
│   ├── schemas.py
│   ├── repository.py
│   └── service.py
│
├── lotes/
│   ├── models.py
│   ├── schemas.py
│   ├── repository.py
│   └── service.py
│
├── ofertas/
│   ├── models.py
│   ├── schemas.py
│   ├── repository.py
│   └── service.py
│
└── usuarios/
    ├── models.py
    ├── schemas.py
    ├── repository.py
    └── service.py
```

La organización por dominio tiene prioridad sobre crear carpetas globales gigantes como `models/`, `services/` o `schemas/` donde termine mezclada toda la lógica del sistema.

---

## 3. Responsabilidad de Cada Capa

El flujo normal de una petición debe ser:

```text
HTTP Request
    ↓
Controller / Route
    ↓
Service
    ↓
Repository
    ↓
SQLAlchemy / PostgreSQL
```

Y para respuestas:

```text
PostgreSQL
    ↓
Repository
    ↓
Service
    ↓
Schema Pydantic
    ↓
Controller / Route
    ↓
HTTP Response
```

### 3.1 Controllers — `api/routes/`

Son la capa HTTP.

Responsabilidades:

- Definir endpoints.
- Recibir parámetros de ruta, query y body.
- Validar contratos mediante schemas Pydantic.
- Obtener la sesión de base de datos.
- Invocar al service correspondiente.
- Devolver el schema de respuesta correcto.
- Manejar aspectos propios del protocolo HTTP.

Reglas:

- **No contienen lógica de negocio.**
- **No ejecutan queries SQL.**
- **No acceden directamente a repositories.**
- No deben decidir cómo se modifica una entidad.
- Deben ser deliberadamente finos.

Ejemplo conceptual:

```python
@router.post("/ofertas")
def crear_oferta(
    datos: OfertaCrear,
    db: Session = Depends(obtener_db),
):
    return servicio_ofertas.crear_oferta(db, datos)
```

La ruta delega; el service decide qué hacer.

---

### 3.2 Services — `domains/<dominio>/service.py`

Son la capa principal de **lógica de aplicación y negocio**.

Responsabilidades:

- Implementar casos de uso.
- Validar reglas de negocio.
- Coordinar múltiples repositories cuando sea necesario.
- Coordinar operaciones entre entidades.
- Controlar transacciones cuando el caso de uso lo requiera.
- Invocar integraciones externas cuando corresponda.
- Lanzar errores de negocio apropiados.

Ejemplos de casos de uso:

```text
crear_emergencia()
publicar_lotes()
crear_oferta()
actualizar_oferta()
crear_consorcio()
cerrar_actividad()
obtener_ofertas_consolidadas()
```

Reglas:

- El service **no debe contener SQL crudo**.
- El service no debe conocer detalles internos de FastAPI más allá de lo estrictamente necesario.
- Las consultas de persistencia deben delegarse al repository.
- Las reglas de negocio deben vivir aquí y no en los controllers.

---

### 3.3 Repositories — `domains/<dominio>/repository.py`

Son la capa de acceso a datos.

Responsabilidades:

- Consultar PostgreSQL mediante SQLAlchemy.
- Crear, modificar y eliminar entidades.
- Ejecutar consultas específicas del dominio.
- Encapsular detalles de persistencia.
- Aplicar consultas con locking cuando el caso de uso lo requiera.

Ejemplos:

```text
obtener_emergencia()
listar_ofertas_de_emergencia()
crear_oferta()
actualizar_oferta()
obtener_versiones_oferta()
```

Reglas:

- Los repositories **no contienen reglas de negocio**.
- No deben decidir si una operación está permitida.
- No deben lanzar decisiones propias de la lógica del sistema.
- Deben concentrarse en persistencia y consultas.

---

### 3.4 Models — `domains/<dominio>/models.py`

Contienen las entidades SQLAlchemy correspondientes al dominio.

Utilizar:

```python
Mapped[]
mapped_column()
```

y las relaciones SQLAlchemy correspondientes cuando sean necesarias.

Reglas:

- Un modelo representa una entidad persistida.
- Las relaciones deben existir únicamente cuando tengan sentido para el dominio.
- No crear modelos "por las dudas".
- Todo modelo nuevo debe quedar correctamente registrado/importado en el mecanismo de inicialización de modelos existente en el proyecto.

---

### 3.5 Schemas — `domains/<dominio>/schemas.py`

Contienen los contratos Pydantic utilizados por la API.

Separar, cuando corresponda:

```text
EntidadBase
EntidadCrear
EntidadActualizar
EntidadRespuesta
```

Utilizar `from_attributes=True` en schemas de respuesta que se construyan desde modelos SQLAlchemy.

Los schemas representan contratos de entrada/salida; **no contienen lógica de negocio**.

---

## 4. Dependencias Permitidas Entre Capas

La dirección de dependencias debe mantenerse:

```text
api/routes
     ↓
service
     ↓
repository
     ↓
SQLAlchemy / PostgreSQL
```

Los schemas pueden ser utilizados por las rutas y services cuando representen contratos de datos.

### Está prohibido:

```text
Route → PostgreSQL
Route → SQLAlchemy query
Route → Repository
Repository → Route
Repository → HTTP
Model → Service
```

La ruta nunca debe saltarse el service para acceder directamente a datos.

### Los services pueden coordinar varios repositories

Por ejemplo:

```text
crear_oferta()
    │
    ├── OfertaRepository
    ├── VersionOfertaRepository
    └── InventarioRepository
```

Esto es válido porque el service está implementando un caso de uso que involucra varios componentes.

---

## 5. Dominios Principales de RescueSync

Los siguientes son los dominios funcionales previstos por el proyecto:

### `usuarios`

Responsable de:

- usuarios;
- roles;
- permisos/RBAC;
- asociación con organización cuando corresponda.

Roles mínimos del sistema:

```text
OPERADOR_MUNICIPAL
CENTRO_COORDINADOR
REPRESENTANTE_ONG
AUDITOR_DIRECTIVO
```

### `emergencias`

Responsable de:

- registro de emergencias;
- gravedad;
- zona afectada;
- descripción;
- estado de la emergencia.

### `lotes`

Responsable de:

- lotes de necesidades;
- recursos requeridos;
- cantidades;
- publicación de convocatorias.

### `ofertas`

Responsable de:

- ofertas de ayuda;
- ofertas parciales;
- actualización de ofertas;
- estado de ofertas;
- consolidación de ofertas para Bonita;
- trazabilidad de versiones.

La aplicación web debe ser la fuente de verdad de las ofertas locales. No deben persistirse borradores/ofertas preliminares en la API nacional.

### `consorcios`

Responsable de:

- asociaciones entre ONGs;
- ofertas conjuntas;
- integrantes del consorcio;
- relación entre consorcio y oferta.

### `inventario`

Responsable de:

- recursos disponibles de las ONGs;
- cantidades disponibles;
- disponibilidad local;
- relación con las ofertas.

### `notificaciones`

Responsable de:

- notificaciones de convocatoria;
- adjudicaciones;
- cambios relevantes de estado.

### `dashboard`

Responsable de:

- consultas agregadas;
- indicadores;
- métricas;
- datos necesarios para reportes.

No debe duplicar innecesariamente la lógica de los demás dominios.

---

## 6. Integración con Bonita BPM

Bonita BPM es un **sistema externo de orquestación**, no una capa interna del dominio.

La integración debe estar aislada en:

```text
app/integrations/bonita/
```

Por ejemplo:

```text
integrations/
└── bonita/
    ├── client.py
    └── schemas.py
```

### Regla de integración

```text
Backend
   │
   ▼
Service
   │
   ▼
Bonita Client
   │
   ▼
Bonita BPM
```

El controller nunca debe realizar directamente llamadas HTTP a Bonita.

El cliente de Bonita debe encargarse exclusivamente de:

- construir requests;
- autenticación requerida;
- enviar requests HTTP;
- interpretar respuestas;
- manejar errores de comunicación.

Las reglas de negocio sobre **cuándo** debe invocarse Bonita pertenecen al service.

### Flujo de ofertas

Cuando Bonita vence el temporizador de convocatoria:

```text
Bonita
   │
   │ GET
   ▼
Backend Web
   │
   ▼
Service de Ofertas
   │
   ▼
Repository de Ofertas
   │
   ▼
PostgreSQL
   │
   ▼
JSON consolidado
   │
   ▼
Bonita
```

---

## 7. API Nacional

La API Nacional es otro sistema independiente.

**No debe convertirse en otro módulo interno del backend local.**

La arquitectura global es:

```text
                    ┌─────────────────┐
                    │  Backend Web    │
                    │  RescueSync     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Bonita BPM    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ API Nacional    │
                    │     Cloud       │
                    └─────────────────┘
```

La API Nacional tiene su propio:

- backend;
- PostgreSQL;
- autenticación JWT;
- Docker;
- Swagger/OpenAPI;
- control de concurrencia;
- locking de recursos.

No compartir directamente la base de datos local con la API Nacional.

---

## 8. Transacciones y Concurrencia

Las operaciones que modifiquen estado de manera crítica deben ejecutarse dentro de una transacción.

En particular, el control de recursos nacionales pertenece a la API Nacional.

Cuando se requiera impedir una condición de carrera, utilizar locking de PostgreSQL mediante SQLAlchemy.

Conceptualmente:

```text
BEGIN
    ↓
SELECT ... FOR UPDATE
    ↓
verificar disponibilidad
    ↓
crear compromiso
    ↓
actualizar recurso
    ↓
COMMIT
```

No implementar locking manual con variables Python, sleeps o flags en memoria.

---

## 9. RBAC

El control de permisos debe existir en el backend.

No alcanza con ocultar botones en el frontend.

Cada endpoint protegido debe verificar que el usuario tenga el rol necesario.

Ejemplo conceptual:

```text
POST /emergencias
    → OPERADOR_MUNICIPAL

POST /emergencias/{id}/lotes
    → CENTRO_COORDINADOR

POST /ofertas
    → REPRESENTANTE_ONG

GET /dashboard
    → AUDITOR_DIRECTIVO
```

Los permisos concretos deben derivarse de los requisitos funcionales de cada tarea y no inventarse arbitrariamente.

---

## 10. Trazabilidad de Ofertas

Las ofertas pueden ser modificadas durante la ventana de convocatoria.

Cuando la tarea requiera trazabilidad, no sobrescribir silenciosamente la información anterior.

El modelo conceptual puede ser:

```text
Oferta
  │
  ├── Versión 1
  ├── Versión 2
  └── Versión 3
```

Cada versión debe permitir identificar, cuando corresponda:

- quién realizó el cambio;
- cuándo;
- qué versión representa;
- los datos de la oferta en ese momento.

No implementar un sistema de versionado completo si la tarea concreta no lo requiere; respetar siempre el principio de alcance mínimo.

---

## 11. Reglas de Diseño del Monolito Modular

- Cada dominio debe ser dueño de sus entidades y reglas.
- Evitar dependencias circulares entre dominios.
- Un dominio no debe acceder directamente a las tablas internas de otro dominio si puede comunicarse mediante un service o caso de uso bien definido.
- No duplicar lógica de negocio entre dominios.
- Las rutas deben permanecer finas.
- Los services deben contener los casos de uso.
- Los repositories deben contener la persistencia.
- Las integraciones externas deben permanecer aisladas.
- No crear abstracciones genéricas innecesarias.
- No crear un "utils.py" gigante para lógica de negocio.
- No crear un service global que concentre toda la aplicación.
- No mover lógica a una capa inferior solamente para evitar escribir código en el service.
- Mantener las responsabilidades claras y pequeñas.

---

## 12. Convenciones de Nombres

Todo el código debe estar en español.

Ejemplos:

```text
emergencia.py
oferta.py
lote.py
usuario.py
consorcio.py

crear_oferta()
actualizar_oferta()
obtener_emergencia()
listar_lotes()
```

Clases:

```text
Emergencia
Oferta
Lote
Usuario
Consorcio
```

Schemas:

```text
EmergenciaCrear
EmergenciaActualizar
EmergenciaRespuesta

OfertaCrear
OfertaActualizar
OfertaRespuesta
```

Repositories:

```text
EmergenciaRepository
OfertaRepository
LoteRepository
```

Services:

```text
EmergenciaService
OfertaService
LoteService
```

No utilizar nombres en inglés para nuevos componentes salvo que formen parte de una API, librería, protocolo o tecnología externa cuyo nombre deba conservarse.

---

## 13. Registro de Rutas

Todos los routers deben incluirse en:

```text
app/main.py
```

utilizando:

```text
API_PREFIX = "/api/v1"
```

Las rutas deben agruparse por dominio.

Ejemplo:

```text
/api/v1/emergencias
/api/v1/lotes
/api/v1/ofertas
/api/v1/usuarios
```

No crear rutas fuera del prefijo establecido salvo que exista un requisito explícito.

---

## 14. Comandos de Verificación Obligatorios

Antes de reportar tu tarea como finalizada, ejecutá en `backend/`:

```bash
python -c "from app.main import app; print('App importada con éxito')"
```

Si hay tests unitarios configurados en el proyecto, ejecutá:

```bash
pytest
```

Si la tarea modifica modelos o migraciones, verificar además que las migraciones sean coherentes con el estado actual de la base de datos.

---

## 15. Formato de Reporte de Cierre

Al finalizar, devolvé al orquestador este formato sin texto superfluo:

- Archivos modificados/creados: (lista de rutas)
- Dominio(s) afectado(s): (lista)
- Caso(s) de uso implementado(s): (lista)
- Contratos expuestos: (Verbo HTTP + Path + Schema Entrada/Salida si aplica)
- Resultado de verificación: Importación de app (OK/ERROR)
- Tests: (OK/ERROR/No configurados)
