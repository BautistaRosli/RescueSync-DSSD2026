# Modificaciones — RescueSync Prioridad (Fases 1 a 5)

**Alcance:** dejar funcionando en Kubernetes **solo** el microservicio `prioridad-service` y
conectarlo con el RescueSync local (backend FastAPI, frontend React, PostgreSQL y Bonita), sin
mover el resto de la aplicación al clúster.

Este documento consolida las respuestas y reportes entregados en cada fase, los cambios aplicados
y las decisiones tomadas, para que cualquier persona pueda entender qué se hizo y por qué.

# Contenido del documento
- Contexto y decisiones de base — situación de partida y tabla de decisiones con su motivo.
- Fase 1 — Auditoría inicial — hallazgos y brechas que motivaron el resto del trabajo.
- Fase 2 — Servicio, tests e imagen — endpoints, validaciones, lógica de cálculo, Dockerfile multi-etapa, usuario no root y tamaño de la imagen.
- Fase 3 — Kubernetes — tabla de los 6 manifiestos, validación (dry-run, kubeconform), Metrics Server, HPA y evidencia del escalado 1→5→1.
- Fase 4 — Ajuste e integración — cambio baja = 1, tests de extremos, re-publicación de la imagen, cliente de prioridad, flujo del backend, frontend, configuración y prueba E2E (incluido el 503 con fallo cerrado).
- Fase 5 — Documentación y validación — DEPLOY.md, VALIDATION.md y estado final del clúster.
- Inventario de archivos — qué se modificó, qué se creó y a qué fase pertenece.
- Decisiones y alternativas descartadas — el “por qué” de cada elección (NodePort, un solo Service, no auditar en BD, critica → alta, timeout 3 s, port-forward, imagePullPolicy: Always).
- Reproducción rápida — comandos para levantar, probar y validar.
- Estado, límites y pendientes — lo verificado y las tareas opcionales que quedan.

---

## 0. Contexto y decisiones de base

### Situación de partida

- Existía un microservicio `prioridad-service` (FastAPI) con su código y manifiestos en el repo.
- El resto de RescueSync corría local con Docker Compose: `fastapi_backend` (8000),
  `react_frontend` (5173), `postgres_db` (5432) y Bonita.
- La prioridad no se usaba en el flujo real de registro de emergencias.

### Decisiones tomadas

| Decisión | Motivo |
| :--- | :--- |
| Solo `prioridad-service` va a Kubernetes | Requisito explícito; el resto sigue local para no romper el entorno de desarrollo. |
| Un único `Service` con **NodePort 30080** | Un solo punto de entrada para todas las réplicas, accesible desde el backend y el frontend. |
| HPA de **1 a 5 réplicas** | Soporta la demo de escalado sin sobredimensionar el clúster local. |
| Imagen pública en Docker Hub (`emiliano754/rescuesync-prioridad:1.0.0`) | El clúster debe poder descargarla sin credenciales. |
| Prioridad entero **1–10 inclusive** | Requisito del contrato; sin preferencia por cliente. |
| Entrada del servicio: **`zona`** | Se mantiene el nombre `zona` en todo el contrato. |
| `critica` se envía como **`alta`** | El servicio solo conoce `alta/media/baja`; se conserva la escala del backend. |
| Prioridad **sin auditoría histórica** | Se devuelve en la respuesta del `POST /emergencias` y se muestra en el frontend; no se agrega columna ni migración. |
| Fallo cerrado | Si K8s no responde en **3 s**, el backend devuelve **503** y no persiste la emergencia ni inicia Bonita. |
| Puente `kubectl port-forward` | Docker Desktop en Windows no publica el NodePort en `localhost`; el port-forward expone `30080 → 80`. |

---

## Fase 1 — Auditoría inicial y brechas

### Qué se hizo

Se revisó el estado del microservicio, sus manifiestos, el `Dockerfile`, los tests y la documentación
existente, contrastándolos con el alcance pedido.

### Hallazgos principales

1. **El rango 1–10 no era alcanzable en el mínimo:** con `baja = 2` y la zona `centro = 0`, el valor
   mínimo posible era **2**. El requisito exige que 1 y 10 sean alcanzables.
2. **El `Service` era `ClusterIP`:** no había forma de consumirlo desde el backend/frontend local.
3. **No existía integración:** el backend no consultaba la prioridad al registrar una emergencia.
4. **Documentación desactualizada** respecto del estado real de despliegue y validación.
5. **Faltaba verificar** probes, `resources`, seguridad del pod y comportamiento del HPA con el
   Metrics Server del clúster local.

### Resultado

Reporte de brechas que definió el plan de las fases 2 a 5.

---

## Fase 2 — Servicio, tests e imagen Docker

### Qué se hizo

- Se completó y verificó el microservicio FastAPI:
  - `GET /health` → `{"status":"ok"}`
  - `GET /ready` → `{"status":"ready"}`
  - `POST /prioridad` → calcula un entero 1–10
  - Validaciones: `gravedad` fuera del enum → **422**; `zona` vacía → **400**.
- Se ejecutaron los tests unitarios y de API: **27 passed** en ese momento.
- Se construyó una imagen **multi-etapa** (`builder` + `runtime`):
  - Usuario no root `appuser` (UID/GID 1001).
  - `HEALTHCHECK` contra `/health`.
  - Tamaño final: **54.1 MiB**.
  - Publicada como `emiliano754/rescuesync-prioridad:1.0.0` y `latest`.

### Lógica de cálculo

```
GRAVEDAD_SCORE = { "baja": 1, "media": 5, "alta": 8 }
ZONA_SCORE     = { "norte": 2, "sur": 2, "este": 1, "oeste": 1, "centro": 0, "periferia": 1 }

prioridad = clamp(GRAVEDAD_SCORE[gravedad] + ZONA_SCORE[zona], 1, 10)
```

- Una zona desconocida usa un valor estable derivado de sus caracteres (`suma % 3`).
- La prioridad depende **solo** de gravedad y zona: nunca del cliente, IP, cabeceras ni estado global.

### Resultado

Imagen funcional y publicada. Quedó identificado que el mínimo real seguía siendo 2 y que el
`Service` aún no servía para el entorno local; ambos puntos se resolvieron en fases posteriores.

---

## Fase 3 — Manifiestos y despliegue en Kubernetes

### Cambios en `k8s/`

| Archivo | Cambio |
| :--- | :--- |
| `00-namespace.yaml` | Namespace `rescuesync`. |
| `01-configmap.yaml` | `LOG_LEVEL=info`, `PORT=8080`. |
| `02-secret.yaml` | Placeholder `API_KEY_INTERNA=cambiar-en-produccion`. |
| `03-deployment.yaml` | 1 réplica inicial, rolling update `maxUnavailable: 0`, `maxSurge: 1`, `runAsNonRoot` UID 1001, `readOnlyRootFilesystem`, `drop ALL`, `seccomp RuntimeDefault`, requests `50m/128Mi`, limits `250m/256Mi`, probes `/health` y `/ready`. |
| `04-service.yaml` | **`ClusterIP` → `NodePort` 80 → 30080**. |
| `05-hpa.yaml` | `minReplicas: 1`, `maxReplicas: 5`, CPU 70 %, memoria 80 %, scale-down con ventana de 300 s. |

### Validación

```bash
kubectl apply --dry-run=client -f k8s/     # 6 recursos, sin errores
kubeconform -strict k8s/                   # 6/6 válidos
kubectl apply -f k8s/                      # 6 recursos creados
kubectl get pods -n rescuesync             # 1/1 Running, 0 restarts
kubectl get svc -n rescuesync              # 80:30080/TCP
```

### Metrics Server y HPA

En Docker Desktop los certificados del kubelet son self-signed, por lo que el Metrics Server se
instaló con `--kubelet-insecure-tls`. Sin ese argumento, el HPA queda en `<unknown>`.

- Estado observado: `cpu: 8%/70%`, `memory: 29%/80%`.
- Prueba de escalado con `fortio` (`-c 30 -t 300s`): **1 → 2 → 3 → 4 → 5**, respetando el tope.
- Al retirar la carga: **5 → 2 → 1** en ~10 minutos (ventana de estabilización de 300 s).

### Resultado

Microservicio desplegado y escalable. Quedaba pendiente el ajuste 1–10 y la integración real con
el backend/frontend.

---

## Fase 4 — Ajuste del rango y integración local

### 4.1 Servicio: `baja = 1`

**Archivo:** `prioridad-service/app/priority.py`

```diff
- GRAVEDAD_SCORE = {"baja": 2, "media": 5, "alta": 8}
+ GRAVEDAD_SCORE = {"baja": 1, "media": 5, "alta": 8}
```

**Archivo:** `prioridad-service/tests/test_priority.py`

Se agregó `test_extremos_del_rango`, que fija el contrato en ambos extremos:

```python
assert calcular_prioridad("baja", "centro") == 1
assert calcular_prioridad("alta", "norte") == 10
```

Resultado: **28 passed**.

### 4.2 Imagen re-publicada

- Se reconstruyó y publicó el mismo tag `1.0.0` (y `latest`).
- Digest nuevo: `sha256:abf1252e6d934ab56c5244d8639093f5072dc0b08de9431d6da61e423766d909`.
- En `k8s/03-deployment.yaml` se cambió `imagePullPolicy` a **`Always`** para que el nodo no
  reutilice la capa anterior del mismo tag.
- Se reinició el rollout y se verificó que el pod corre con el digest nuevo.

### 4.3 Cliente de prioridad en el backend

**Archivos nuevos:** `backend/app/integrations/prioridad/__init__.py` y `client.py`

- `httpx.AsyncClient` con **timeout de 3 s**.
- URL tomada de `PRIORIDAD_SERVICE_URL` (default `http://localhost:30080`).
- Mapea `critica → alta` antes de enviar.
- Valida que la respuesta sea un entero entre **1 y 10** (rechaza `bool` explícitamente).
- Cualquier error de conexión, HTTP distinto de 200, JSON inválido o valor fuera de rango lanza
  `PrioridadClientError`.

### 4.4 Flujo de creación de emergencias

**Archivo:** `backend/app/services/emergencias_service.py`

- `crear_emergencia` pasó a ser `async` y consulta la prioridad **antes de persistir**.
- Si falla, registra el error y lanza `HTTPException(503, "No se pudo obtener la prioridad de la
  emergencia")`.
- Si funciona, crea la emergencia, adjunta `prioridad` a la respuesta y programa la notificación.

**Archivo:** `backend/app/api/routes/emergencias_api.py`

- La ruta `POST /emergencias` espera el servicio con `await`.
- Propaga `prioridad` al DTO final que se devuelve al cliente.

**Archivo:** `backend/app/dto/emergencias_dto.py`

- Se agregó `prioridad: Optional[int] = None` a `EmergenciaRespuesta`.

La prioridad **no se guarda en la base de datos**: viaja solo en la respuesta HTTP.

### 4.5 Frontend

| Archivo | Cambio |
| :--- | :--- |
| `frontend/src/types/emergencia.ts` | `prioridad?: number \| null` en `EmergenciaCreada`. |
| `frontend/src/pages/RegistrarEmergenciaPage.tsx` | Fila “Prioridad” en la confirmación, con valor `N/10` o `—` si no vino. |

Verificación: `bun run lint` **OK** y `bun run build` **OK**.

### 4.6 Configuración del entorno

| Archivo | Cambio |
| :--- | :--- |
| `docker-compose.yml` | `PRIORIDAD_SERVICE_URL=http://host.docker.internal:30080` en el backend. |
| `backend/.env.example` | `PRIORIDAD_SERVICE_URL=http://localhost:30080` documentada para ejecución nativa. |

### 4.7 Tests del backend

**Archivo:** `backend/tests/test_permisos_api.py`

- Se mockeó `prioridad_client.obtener_prioridad` con `AsyncMock(return_value=7)` para que la suite
  no dependa del clúster.

### 4.8 Prueba E2E

Con el backend recreado (`docker compose up -d backend`) y el port-forward activo:

```bash
kubectl port-forward --address 0.0.0.0 -n rescuesync svc/rescuesync-prioridad-svc 30080:80
```

**Éxito:**

```http
POST /api/v1/emergencias
{"nivel_gravedad":"critica","zona_afectada":"zona-norte-e2e","descripcion_inicial":"..."}

201 Created
{ "id": 4, ..., "prioridad": 10 }
```

`critica` se envió como `alta` y `zona-norte-e2e` cayó en la zona `norte`, por eso el máximo.

**Fallo cerrado:**

Se detuvo el port-forward y se repitió el POST:

```http
503 Service Unavailable
{"detail":"No se pudo obtener la prioridad de la emergencia"}
```

Se verificó con `GET /api/v1/emergencias` que la emergencia fallida **no quedó registrada**.

---

## Fase 5 — Documentación y validación final

### 5.1 `DEPLOY.md`

Se reescribió para reflejar el estado real:

- Prerrequisitos y Metrics Server (`--kubelet-insecure-tls`).
- Imagen pública y publicación.
- Despliegue y verificación en un solo bloque.
- Acceso local: NodePort en Linux/cloud y **port-forward** en Docker Desktop Windows.
- Integración con el backend (`PRIORIDAD_SERVICE_URL`, `critica → alta`, timeout y 503).
- Demostración de escalado y limpieza.
- Troubleshooting (HPA `<unknown>`, `ImagePullBackOff`, NodePort inaccesible, 503).

Extensión final: **105 líneas** (~2 carillas).

### 5.2 `VALIDATION.md`

Se actualizó con los datos definitivos:

- 28 tests del servicio.
- Digest nuevo de la imagen.
- `Service` NodePort `80:30080`.
- Extremos 1 y 10 verificados.
- Integración E2E y fallo cerrado.
- HPA `1/5` con CPU y memoria reales.
- Nota sobre `imagePullPolicy: Always` y sobre el puente port-forward.
- Fallos preexistentes del backend, ajenos a la integración.

### 5.3 Estado final verificado

```
deployment.apps/rescuesync-prioridad   1/1   1   1
rescuesync-prioridad-hpa   cpu: 6%/70%, memory: 29%/80%   1   5   1
rescuesync-prioridad-svc   NodePort   10.96.209.195   80:30080/TCP
pod/rescuesync-prioridad-...   1/1   Running   0 restarts
```

---

## Inventario de archivos

### Modificados y aún sin commitear

| Archivo | Fase | Cambio |
| :--- | :--- | :--- |
| `prioridad-service/app/priority.py` | 4 | `baja` pasa de 2 a 1. |
| `prioridad-service/tests/test_priority.py` | 4 | Test de extremos 1 y 10. |
| `k8s/03-deployment.yaml` | 4 | `imagePullPolicy: Always`. |
| `k8s/04-service.yaml` | 3 | `ClusterIP` → `NodePort 30080`. |
| `backend/app/services/emergencias_service.py` | 4 | Consulta de prioridad y 503. |
| `backend/app/api/routes/emergencias_api.py` | 4 | `await` y propagación de `prioridad`. |
| `backend/app/dto/emergencias_dto.py` | 4 | Campo `prioridad` en la respuesta. |
| `backend/tests/test_permisos_api.py` | 4 | Mock del cliente de prioridad. |
| `docker-compose.yml` | 4 | `PRIORIDAD_SERVICE_URL` del backend. |
| `backend/.env.example` | 4 | Variable documentada. |
| `frontend/src/types/emergencia.ts` | 4 | Tipo `prioridad`. |
| `frontend/src/pages/RegistrarEmergenciaPage.tsx` | 4 | Muestra “Prioridad N/10”. |
| `DEPLOY.md` | 5 | Guía de despliegue actualizada. |
| `VALIDATION.md` | 5 | Validación final actualizada. |

### Nuevos

| Archivo | Fase | Contenido |
| :--- | :--- | :--- |
| `backend/app/integrations/prioridad/__init__.py` | 4 | Paquete de integración. |
| `backend/app/integrations/prioridad/client.py` | 4 | Cliente HTTP con timeout, mapeo y validación 1–10. |
| `modificaciones.md` | 5 | Este documento. |

> Los artefactos de las Fases 1–3 (`prioridad-service/`, `k8s/`, imagen) ya están versionados en git.
> Los cambios de las Fases 4–5 están en el working tree, sin commit.

---

## Decisiones y alternativas descartadas

| Decisión | Alternativa descartada | Por qué |
| :--- | :--- | :--- |
| NodePort 30080 | `LoadBalancer` o `Ingress` | En Docker Desktop el `LoadBalancer` queda en `<pending>` y el Ingress agrega complejidad innecesaria. |
| Un solo `Service` | Un Service por réplica | El Service ya balancea entre réplicas; no hace falta más. |
| Prioridad solo en la respuesta | Nueva columna/tabla de auditoría | El requisito pedía la solución más simple y sin auditoría histórica. |
| `critica → alta` en el backend | Agregar `critica` al servicio | Evita romper el contrato del microservicio y mantiene la escala existente. |
| Timeout 3 s + 503 | Reintentos o fallback local | Fallo cerrado: es preferible no registrar una emergencia sin prioridad antes que inventarla. |
| Port-forward como puente | Publicar el NodePort en `localhost` | Docker Desktop Windows no lo publica; el port-forward es el mecanismo documentado y confiable. |
| `imagePullPolicy: Always` | Nuevo tag `1.0.1` | Se pidió mantener la versión `1.0.0`; `Always` fuerza el pull del digest nuevo. |

---

## Reproducción rápida

```bash
# 1. Clúster e imagen
kubectl apply -f k8s/
kubectl rollout status deployment/rescuesync-prioridad -n rescuesync

# 2. Puente local
kubectl port-forward --address 0.0.0.0 -n rescuesync svc/rescuesync-prioridad-svc 30080:80

# 3. Backend con la variable de entorno
docker compose up -d backend

# 4. Verificación directa
curl -X POST http://localhost:30080/prioridad \
  -H "Content-Type: application/json" -d '{"gravedad":"baja","zona":"centro"}'   # 1
curl -X POST http://localhost:30080/prioridad \
  -H "Content-Type: application/json" -d '{"gravedad":"alta","zona":"norte"}'    # 10

# 5. Tests
pytest -q prioridad-service      # 28 passed
```

---

## Estado, límites y pendientes

### Verificado

- 28 tests del microservicio en verde.
- Extremos 1 y 10 alcanzables y probados.
- Despliegue, probes, seguridad del pod y HPA funcionando.
- Escalado 1→5→1 validado.
- Integración E2E: `critica` + `norte` → prioridad 10.
- Fallo cerrado: servicio caído → 503 y sin persistencia.
- Frontend compila y muestra la prioridad.

### Límites conocidos

- El `port-forward` debe permanecer activo para la demo; si se corta, el backend responde 503
  (comportamiento intencional).
- El `Secret` versionado contiene solo un placeholder.
- La prioridad no queda auditada en la base de datos; solo se ve en la respuesta y en la UI.

### Pendientes opcionales (fuera del alcance)

1. Hacer commit de los cambios de Fases 4–5.
2. Borrar la emergencia de prueba `id 4` (`zona-norte-e2e`) de la base de desarrollo.
3. Corregir 4 tests preexistentes del backend, ajenos a esta integración:
   - 3 de `iniciar_proceso_bonita` (validación de lotes comentada y `set_case_variables` ausente).
   - 1 de permisos de ofertas consolidadas (`REPRESENTANTE_ONG` recibe 200 en lugar de 403).
4. Verificación visual en navegador de la fila “Prioridad”.
