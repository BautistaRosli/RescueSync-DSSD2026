# RescueSync — Especificación de Implementación para Agente IA

> **Uso de este documento:** Este documento está estructurado para que un agente orquestador pueda dividir el trabajo en **5 sub‑agentes** que corren en paralelo o secuencialmente según sus dependencias.

---

## 1. Contexto del proyecto

**RescueSync** es una plataforma para coordinar la respuesta ante desastres naturales. Los municipios afectados envían una petición a un servicio de la organización informando **nivel de gravedad** y **zona afectada**. El servicio devuelve un **número de prioridad entre 1 y 10** (10 = más prioritario, 1 = menos). Con ese número, el municipio queda habilitado a registrar la emergencia formalmente.

**Restricciones de negocio (del enunciado):**

- Las emergencias pueden registrarse desde cualquier lugar y horario → el servicio debe ser **stateless** y **siempre disponible**.
- Hay picos abruptos de tráfico → requiere **escalado automático**.
- Consumo de recursos eficiente (costos) → `requests`/`limits` ajustados + HPA con `minReplicas` bajo.
- Todas las peticiones llegan a **un mismo servicio** con **mínimo 1 y máximo 5 réplicas** → `Service` + `HPA` con `min=1`, `max=5`.
- **No hay prioridad por cliente**; la prioridad depende solo de **gravedad + zona**.
- Salida: entero entre **1 y 10**.

**Entregables obligatorios:**

1. Código fuente del servicio de prioridad.
2. `Dockerfile` del servicio.
3. Imagen publicada en **DockerHub** (pública).
4. Archivos YAML de Kubernetes (Deployment, Service, HPA, ConfigMap, Secret, probes).
5. Documento de despliegue (**máximo 2 carillas**) con comandos y acciones.

**Nota:** el `docker-compose.yml` actual solo sirve como entorno local de desarrollo; **no cuenta como entregable Kubernetes**.

---

## 2. Arquitectura objetivo

```
┌─────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                    │
│                                                              │
│  ┌──────────────────┐                                        │
│  │  Service (ClusterIP)                                    │
│  │  rescuesync-prioridad-svc                               │
│  └────────┬─────────────────────────────────────────────┘  │
│           │                                                  │
│  ┌────────▼─────────┐   ┌────────────────────┐              │
│  │  Deployment      │◄──│  HPA (min=1,max=5) │              │
│  │  rescuesync-api  │   └────────────────────┘              │
│  │  (1..5 pods)     │                                       │
│  └────────┬─────────┘                                       │
│           │                                                  │
│  ┌────────▼─────────┐   ┌──────────────────┐                │
│  │  ConfigMap       │   │  Secret          │                │
│  └──────────────────┘   └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

- **Sin base de datos** en el path crítico: la lógica de prioridad es pura y determinista. Si se agrega persistencia para el registro formal, va **fuera** del scope de esta extensión (o en un `StatefulSet` documentado como opcional).
- **Sin estado** en los pods → escalado horizontal trivial.

---

## 3. Desglose en sub‑agentes

| ID | Sub‑agente | Depende de | Produce |
|----|-----------|-----------|---------|
| **SA1** | Backend Service Developer | — | Código del servicio + tests |
| **SA2** | Container Engineer | SA1 | `Dockerfile`, `.dockerignore`, imagen en DockerHub |
| **SA3** | Kubernetes Manifest Engineer | SA2 (tag de imagen) | Todos los YAML de K8s |
| **SA4** | Documentation Writer | SA3 (comandos finales) | `DEPLOY.md` (≤ 2 carillas) |
| **SA5** | QA / Integrador | SA1–SA4 | Reporte de validación end‑to‑end |

> **SA1, SA2, SA3, SA4 pueden correr en paralelo con coordinación de contratos.** SA5 corre al final. La coordinación se hace mediante **contratos fijos** definidos en cada sección (puerto, nombre de imagen, labels, rutas).

---

## 4. Contratos compartidos (obligatorios)

Todos los sub‑agentes deben respetar estos valores para evitar retrabajo:

| Elemento | Valor |
|---|---|
| Nombre del servicio | `rescuesync-prioridad` |
| Namespace K8s | `rescuesync` |
| Puerto interno del contenedor | `8080` |
| Endpoint principal | `POST /prioridad` |
| Endpoint de salud | `GET /health` |
| Imagen DockerHub | `emiliano754/rescuesync-prioridad:1.0.0` |
| Label selector | `app: rescuesync-prioridad` |
| `Service` name | `rescuesync-prioridad-svc` |
| Deployment name | `rescuesync-prioridad` |
| HPA name | `rescuesync-prioridad-hpa` |
| Variables de entorno | `LOG_LEVEL`, `PORT` |

---

## 5. Especificación por sub‑agente

### 🐍 SA1 — Backend Service Developer

**Objetivo:** crear el microservicio que implementa la lógica de prioridad.

**Stack sugerido:** Python 3.12 + FastAPI + Uvicorn (stateless, ligero, ideal para K8s).

**Archivos a producir:**

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # app FastAPI, rutas, health
│   ├── schemas.py       # modelos Pydantic
│   └── priority.py      # lógica de prioridad (función pura)
├── tests/
│   ├── test_priority.py
│   └── test_api.py
├── requirements.txt
└── README.md
```

**Contrato de API:**

- `POST /prioridad`
  - Request body:
    ```json
    { "gravedad": "alta|media|baja", "zona": "string no vacío" }
    ```
  - Response 200:
    ```json
    { "prioridad": 1, "gravedad": "...", "zona": "...", "timestamp": "ISO-8601" }
    ```
    (donde `prioridad` es un entero en `[1,10]`)
  - Response 422 si falta un campo o `gravedad` no está en el enum.
  - Response 400 si `zona` es vacía.
- `GET /health` → `{ "status": "ok" }`, siempre 200 si el proceso está arriba.
- `GET /ready` → `{ "status": "ready" }` (puede ser igual a `/health`; separado para claridad).

**Lógica de prioridad (función pura, determinista, sin estado, sin prioridad por cliente):**

Implementar en `priority.py` una función `calcular_prioridad(gravedad: str, zona: str) -> int` con la siguiente fórmula sugerida (documentada y testeada):

```python
GRAVEDAD_SCORE = {"baja": 2, "media": 5, "alta": 8}  # 0..8
# Modificador de zona: catálogo fijo, NO por cliente.
ZONA_SCORE = {
    "norte": 2, "sur": 2, "este": 1, "oeste": 1,
    "centro": 0, "periferia": 1,
}
# Fallback determinista para zonas desconocidas: hash estable módulo 3.
def _zona_score(zona: str) -> int:
    return ZONA_SCORE.get(zona.strip().lower(),
                         sum(ord(c) for c in zona.lower()) % 3)
def calcular_prioridad(gravedad: str, zona: str) -> int:
    raw = GRAVEDAD_SCORE[gravedad.lower()] + _zona_score(zona)
    return max(1, min(10, raw))
```

> **Justificación:** cumple "no prioridad por cliente" (solo variables del evento) y respeta el rango 1–10. El sub‑agente puede refinar el catálogo de zonas, pero **no** puede introducir identificadores de cliente en la fórmula.

**Tests mínimos (pytest):**

- Prioridad siempre en `[1,10]` para todas las combinaciones del enum × zonas del catálogo.
- `alta`+`norte` > `baja`+`centro`.
- Misma entrada → misma salida (determinismo).
- `/prioridad` responde 422 con payload inválido.
- `/health` responde 200.

**Restricciones:**

- El servicio **debe escuchar en `PORT` (env var, default `8080`)**, host `0.0.0.0`.
- Logs a stdout en formato JSON (una línea por request).
- Sin escritura a disco, sin estado global mutable.
- `requirements.txt` con versiones pinneadas.

**Criterio de aceptación SA1:** `pytest` en verde y `uvicorn app.main:app` levanta y responde `/health`.

---

### 🐳 SA2 — Container Engineer

**Objetivo:** dockerizar el servicio y publicarlo en DockerHub.

**Dependencias:** SA1 (código en `backend/`).

**Archivos a producir:**

```
backend/
├── Dockerfile
└── .dockerignore
```

**Especificación del `Dockerfile`:**

- **Multi‑etapa**:
  - Stage 1 (`builder`): `python:3.12-slim`, instala `build-essential` si hace falta, `pip install --user -r requirements.txt`.
  - Stage 2 (`runtime`): `python:3.12-slim`, copia solo el `site-packages` y el código de la app.
- **Usuario no root**: crear `appuser` (UID 1001) y `USER appuser`.
- **`EXPOSE 8080`**.
- **`HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"`**.
- **`CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]`**.
- `.dockerignore`: `__pycache__`, `.pytest_cache`, `.venv`, `tests/`, `*.md`, `.git`.

**Comandos a ejecutar y documentar:**

```bash
docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./backend
docker tag emiliano754/rescuesync-prioridad:1.0.0 emiliano754/rescuesync-prioridad:latest
docker login
docker push emiliano754/rescuesync-prioridad:1.0.0
docker push emiliano754/rescuesync-prioridad:latest
```

**Criterio de aceptación SA2:**

- `docker run -p 8080:8080 emiliano754/rescuesync-prioridad:1.0.0` responde `/health`.
- La imagen pesa < 300 MB.
- `docker inspect` muestra `User` distinto de `root`.
- La imagen está pública en `https://hub.docker.com/r/emiliano754/rescuesync-prioridad`.

---

### ☸️ SA3 — Kubernetes Manifest Engineer

**Objetivo:** escribir todos los manifiestos K8s que cumplan el enunciado.

**Dependencias:** SA2 (tag de imagen confirmado).

**Estructura a producir:**

```
k8s/
├── 00-namespace.yaml
├── 01-configmap.yaml
├── 02-secret.yaml
├── 03-deployment.yaml
├── 04-service.yaml
├── 05-hpa.yaml
└── kustomization.yaml    # opcional, para `kubectl apply -k k8s/`
```

**Detalle por archivo:**

#### `00-namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rescuesync
```

#### `01-configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: rescuesync-prioridad-config
  namespace: rescuesync
data:
  LOG_LEVEL: "info"
  PORT: "8080"
```

#### `02-secret.yaml`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rescuesync-prioridad-secret
  namespace: rescuesync
type: Opaque
stringData:
  API_KEY_INTERNA: "cambiar-en-produccion"
```

> **Nota:** aunque hoy no se use, demuestra el uso correcto de `Secret` y permite inyectar credenciales futuras. Documentar que en producción se crea con `kubectl create secret` y no se commitea.

#### `03-deployment.yaml`

Requisitos:

- `replicas: 1` (el HPA lo controla; valor inicial bajo por eficiencia).
- `strategy: RollingUpdate` con `maxUnavailable: 0`, `maxSurge: 1`.
- `selector.matchLabels: { app: rescuesync-prioridad }`.
- `template.metadata.labels: { app: rescuesync-prioridad }`.
- **`resources`**:
  ```yaml
  requests: { cpu: "50m", memory: "128Mi" }
  limits:   { cpu: "250m", memory: "256Mi" }
  ```
- **Probes**:
  ```yaml
  livenessProbe:
    httpGet: { path: /health, port: 8080 }
    initialDelaySeconds: 10
    periodSeconds: 15
    failureThreshold: 3
  readinessProbe:
    httpGet: { path: /ready, port: 8080 }
    initialDelaySeconds: 5
    periodSeconds: 10
    failureThreshold: 2
  ```
- **`securityContext`** a nivel pod y contenedor:
  ```yaml
  runAsNonRoot: true
  runAsUser: 1001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: { drop: ["ALL"] }
  ```
- **`envFrom`** desde `ConfigMap` + `Secret`.
- **`imagePullPolicy: IfNotPresent`**.
- **`terminationGracePeriodSeconds: 30`**.

#### `04-service.yaml`

- `type: ClusterIP`.
- `selector: { app: rescuesync-prioridad }`.
- `port: 80`, `targetPort: 8080`, `protocol: TCP`.
- `name: rescuesync-prioridad-svc`.

> Si se necesita exponer externamente, agregar un segundo manifiesto opcional `04b-ingress.yaml` (opcional, no obligatorio).

#### `05-hpa.yaml` (clave del cumplimiento)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: rescuesync-prioridad-hpa
  namespace: rescuesync
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rescuesync-prioridad
  minReplicas: 1
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Pods
          value: 1
          periodSeconds: 30
```

- **`minReplicas: 1` y `maxReplicas: 5` son obligatorios y no negociables.**
- Documentar que requiere **Metrics Server** instalado.

**Criterio de aceptación SA3:**

- `kubectl apply --dry-run=client -f k8s/` sin errores.
- `kubectl get hpa -n rescuesync` muestra `MINPODS=1` y `MAXPODS=5`.
- `kubectl describe hpa -n rescuesync rescuesync-prioridad-hpa` sin warnings críticos.

---

### 📄 SA4 — Documentation Writer

**Objetivo:** producir `DEPLOY.md` (máximo 2 carillas) con comandos reproducibles.

**Dependencias:** SA1–SA3 (comandos finales, imagen publicada).

**Contenido obligatorio de `DEPLOY.md`:**

1. **Prerrequisitos**
   - `kubectl` configurado contra un clúster (minikube, kind, EKS, GKE, etc.).
   - **Metrics Server** instalado (imprescindible para HPA):
     ```bash
     kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
     kubectl get apiservice v1beta1.metrics.k8s.io
     ```
   - Acceso a DockerHub (`docker login`) solo si se reconstruye la imagen.
2. **Construcción y publicación de imagen** (si no se usa la ya publicada):
   ```bash
   docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./backend
   docker push emiliano754/rescuesync-prioridad:1.0.0
   ```
3. **Despliegue de manifiestos**:
   ```bash
   kubectl apply -f k8s/00-namespace.yaml
   kubectl apply -f k8s/01-configmap.yaml
   kubectl apply -f k8s/02-secret.yaml
   kubectl apply -f k8s/03-deployment.yaml
   kubectl apply -f k8s/04-service.yaml
   kubectl apply -f k8s/05-hpa.yaml
   ```
4. **Verificación**:
   ```bash
   kubectl get pods -n rescuesync
   kubectl get svc -n rescuesync
   kubectl get hpa -n rescuesync            # MINPODS=1  MAXPODS=5
   kubectl describe hpa -n rescuesync rescuesync-prioridad-hpa
   kubectl logs -n rescuesync -l app=rescuesync-prioridad --tail=50
   ```
5. **Prueba funcional** (con `port-forward` para no depender de Ingress):
   ```bash
   kubectl port-forward -n rescuesync svc/rescuesync-prioridad-svc 8080:80 &
   curl -X POST http://localhost:8080/prioridad \
     -H "Content-Type: application/json" \
     -d '{"gravedad":"alta","zona":"norte"}'
   # respuesta esperada: {"prioridad":10,...}
   curl http://localhost:8080/health
   ```
6. **Demostración de escalado** (opcional pero recomendado):
   ```bash
   kubectl run -n rescuesync load --image=busybox --restart=Never -- \
     sh -c "while true; do wget -q -O- http://rescuesync-prioridad-svc/health; done"
   kubectl get hpa -n rescuesync -w        # ver cómo sube hasta 5
   kubectl delete pod -n rescuesync load
   ```
7. **Limpieza**:
   ```bash
   kubectl delete namespace rescuesync
   ```
8. **Troubleshooting** breve: HPA sin métricas (Metrics Server ausente), `ImagePullBackOff` (imagen privada/mal tag), probes fallando (puerto incorrecto).

**Restricción:** el documento **no debe superar 2 carillas** (usar bloques de código compactos, sin prosa excesiva).

---

### ✅ SA5 — QA / Integrador

**Objetivo:** validar end‑to‑end y producir `VALIDATION.md` con el resultado.

**Checklist a verificar:**

- [ ] `pytest` en `backend/` pasa al 100%.
- [ ] `docker build` produce imagen < 300 MB y corre como non‑root.
- [ ] La imagen responde `/health` y `/prioridad` correctamente en local.
- [ ] La imagen está pública en DockerHub con el tag `1.0.0`.
- [ ] `kubectl apply -f k8s/` sin errores.
- [ ] `kubectl get hpa -n rescuesync` → `MINPODS=1`, `MAXPODS=5`.
- [ ] `kubectl get pods -n rescuesync` → todos `Running` y `Ready`.
- [ ] `kubectl describe hpa` muestra métricas reales (`cpu: X%/70%`), no `<unknown>`.
- [ ] Llamada real vía `port-forward` devuelve entero en `[1,10]`.
- [ ] Bajo carga sostenida el HPA escala hasta 5 y no más.
- [ ] Al cesar la carga, el HPA baja a 1.
- [ ] `DEPLOY.md` ≤ 2 carillas (verificar contando páginas exportando a PDF).
- [ ] El repo no commitea secretos reales (solo placeholders).

**Salida:** `VALIDATION.md` con tabla `check | comando | resultado esperado | resultado obtenido | estado`.

---

## 6. Estructura final del repositorio

```
rescuesync-prioridad/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── priority.py
│   ├── tests/
│   │   ├── test_priority.py
│   │   └── test_api.py
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements.txt
│   └── README.md
├── k8s/
│   ├── 00-namespace.yaml
│   ├── 01-configmap.yaml
│   ├── 02-secret.yaml
│   ├── 03-deployment.yaml
│   ├── 04-service.yaml
│   └── 05-hpa.yaml
├── docker-compose.yml        # opcional, solo dev local
├── DEPLOY.md                 # ≤ 2 carillas
├── VALIDATION.md             # reporte de QA
└── README.md                 # índice general
```

---

## 7. Orden de ejecución recomendado

```
SA1 (código) ──► SA2 (Dockerfile + push) ──► SA3 (YAMLs) ──► SA4 (docs) ──► SA5 (QA)
                        │
                        └──► puede paralelizarse con SA3 una vez fijado el tag de imagen
```

- **Paralelizable:** SA3 y SA4 pueden arrancar en cuanto SA2 confirme `emiliano754/rescuesync-prioridad:1.0.0` publicado.
- **Bloqueante:** SA5 no arranca hasta que SA1–SA4 estén completos.

---

## 8. Prompt sugerido para el agente orquestador

> "Ejecutá la especificación del archivo `tasks.md`. Divide el trabajo en los 5 sub‑agentes definidos (SA1–SA5), respetando los contratos compartidos de la sección 4. Los sub‑agentes pueden correr en paralelo cuando la tabla de dependencias lo permita. Al finalizar, producí `VALIDATION.md` con el checklist de SA5 completamente verificado. Si algún sub‑agente no puede cumplir un criterio de aceptación, detenete y reportá el bloqueo antes de continuar."

---

## 9. Notas para el agente

- **No** incluir credenciales reales en `02-secret.yaml`; usar placeholders.
- **No** usar `latest` como único tag; siempre `1.0.0` versionado.
- **No** introducir dependencia de base de datos en el path de `/prioridad` (rompe el requisito de stateless y simplicidad).
- **Sí** documentar que `docker-compose.yml` es solo para dev local.
- **Sí** dejar el código de `priority.py` con docstring explicando que la prioridad depende solo de gravedad + zona (no de cliente).
- **Sí** incluir `LICENSE` o nota de autoría si el repo es público.