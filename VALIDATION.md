# Validación — RescueSync Prioridad en Kubernetes

**Fecha:** 2026-11-20
**Entorno:** Windows 11 · Docker 29.5.2 · Kubernetes de Docker Desktop v1.34.3 (nodo `desktop-control-plane`) · Metrics Server v0.9.1
**Imagen:** `emiliano754/rescuesync-prioridad:1.0.0` · digest `sha256:abf1252e6d934ab56c5244d8639093f5072dc0b08de9431d6da61e423766d909`

## Resultados

| Check | Comando | Esperado | Obtenido | Estado |
| :--- | :--- | :--- | :--- | :--- |
| Tests unitarios | `pytest -q prioridad-service` | 100 % verde | 28 passed | ✅ |
| Build de imagen | `docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./prioridad-service` | Sin errores | Build OK; HEALTHCHECK `healthy` | ✅ |
| Tamaño de imagen | `docker image inspect ...` | < 300 MB | 54.1 MiB | ✅ |
| Usuario no root | `docker inspect --format "{{.Config.User}}" ...` | ≠ root | `appuser` (UID/GID 1001) | ✅ |
| Salud local | `GET /health`, `GET /ready` | 200 | 200 `{"status":"ok"}` / `{"status":"ready"}` | ✅ |
| Extremos del rango | `POST /prioridad` `{"gravedad":"baja","zona":"centro"}` y `{"gravedad":"alta","zona":"norte"}` | 1 y 10 | 200, `prioridad: 1` y `prioridad: 10` | ✅ |
| Validación 422 | `gravedad: "critica"` | 422 | 422 | ✅ |
| Validación 400 | `zona: "   "` | 400 | 400 `La zona no puede estar vacía` | ✅ |
| Imagen pública | Docker Hub API | pública, tag `1.0.0` | `private=False`, push de `1.0.0` y `latest` OK | ✅ |
| Manifiestos | `kubectl apply --dry-run=client -f k8s/` | Sin errores | 6 recursos creados (dry run) | ✅ |
| Esquema YAML | `kubeconform -strict k8s/` | 0 inválidos | 6/6 válidos | ✅ |
| Despliegue | `kubectl apply -f k8s/` | Sin errores | 6 recursos creados | ✅ |
| Pods | `kubectl get pods -n rescuesync` | Running y Ready | `1/1 Running`, 0 restarts | ✅ |
| Service | `kubectl get svc -n rescuesync` | NodePort 80→30080 | `rescuesync-prioridad-svc` `80:30080/TCP` | ✅ |
| HPA límites | `kubectl get hpa -n rescuesync` | MINPODS=1, MAXPODS=5 | `1` y `5` | ✅ |
| HPA métricas | `kubectl describe hpa` | cpu real, no `<unknown>` | `cpu: 6%/70%`, `memory: 29%/80%`, 1 réplica | ✅ |
| Prueba vía NodePort | `port-forward svc/... 30080:80` + `curl` | entero en [1,10] | `prioridad: 1` y `prioridad: 10`, HTTP 200 | ✅ |
| Integración backend | `POST /api/v1/emergencias` `critica` + `zona-norte-e2e` | 201 con prioridad 10 | 201, `"prioridad": 10` | ✅ |
| Fallo cerrado | mismo POST sin port-forward | 503 y sin persistir | 503 `No se pudo obtener la prioridad…`; no se creó la emergencia | ✅ |
| Escalado bajo carga | `fortio load -c 30 -t 300s` | sube hasta 5 y no más | 1→2→3→4→5; se mantuvo en 5 | ✅ |
| Descenso al cesar carga | observación del HPA | vuelve a 1 | 5→2→1 en ~10 min (stabilization 300 s) | ✅ |
| Secret sin credenciales reales | `kubectl get secret ... -o jsonpath` | solo placeholder | `API_KEY_INTERNA=cambiar-en-produccion` | ✅ |
| `DEPLOY.md` | longitud del documento | ≤ 2 carillas | compacto, NodePort + integración + troubleshooting | ✅ |
| Repo sin secretos reales | revisión de `k8s/` y `.env` | solo placeholders | `.env` ignorado por git; Secret con placeholder | ✅ |

## Evidencia del escalado

```
[ 40s] pods=2 | cpu: 500%/70%  min=1 max=5 replicas=1
[ 60s] pods=2 | cpu: 542%/70%  min=1 max=5 replicas=2
[ 80s] pods=3 | cpu: 266%/70%  min=1 max=5 replicas=3
[100s] pods=4 | cpu: 253%/70%  min=1 max=5 replicas=3
[120s] pods=4 | cpu: 274%/70%  min=1 max=5 replicas=4
[140s] pods=5 | cpu: 139%/70%  min=1 max=5 replicas=5   ← tope respetado
...
[carga retirada]
[330s] pods=2 | cpu: 4%/70%
[600s] pods=1 | cpu: 5%/70%
```

## Evidencia de integración

```
$ curl -X POST http://localhost:30080/prioridad -d '{"gravedad":"baja","zona":"centro"}'
{"prioridad":1,"gravedad":"baja","zona":"centro",...}

$ curl -X POST http://localhost:30080/prioridad -d '{"gravedad":"alta","zona":"norte"}'
{"prioridad":10,"gravedad":"alta","zona":"norte",...}

$ POST /api/v1/emergencias  {"nivel_gravedad":"critica","zona_afectada":"zona-norte-e2e",...}
201 {"id":4,...,"prioridad":10}

# Con el port-forward detenido:
$ POST /api/v1/emergencias  → 503 {"detail":"No se pudo obtener la prioridad de la emergencia"}
$ GET  /api/v1/emergencias  → la emergencia fallida no quedó registrada
```

El backend mapea `zona_afectada → zona` y `critica → alta`, valida el entero 1–10 y usa un
timeout de 3 s. La prioridad se devuelve en la respuesta y se muestra en el frontend
(`Prioridad N/10`); no se persiste ni requiere migración de base de datos.

## Evidencia final

```
$ kubectl get deploy,hpa,svc -n rescuesync
deployment.apps/rescuesync-prioridad   1/1   1   1
rescuesync-prioridad-hpa   cpu: 6%/70%, memory: 29%/80%   1   5   1
rescuesync-prioridad-svc   NodePort   10.96.209.195   80:30080/TCP
```

## Desviaciones y notas

1. **Ubicación del código:** se usó `prioridad-service/` en la raíz (no `backend/`) para no pisar el backend existente del proyecto. El `Dockerfile` y los manifiestos referencian esa ruta.
2. **`pytest.ini` propio** en `prioridad-service/`: el `pytest.ini` raíz fija `testpaths = backend/tests`; el archivo local aísla los tests del servicio y define `pythonpath = .`.
3. **Metrics Server:** en clústeres locales con certificados self-signed (Docker Desktop, Kind) requiere `--kubelet-insecure-tls`. Sin él, el HPA queda en `<unknown>`. Documentado en `DEPLOY.md`.
4. **Clúster validado:** Docker Desktop en lugar de Kind (Kind no estaba instalado al momento de validar). Los manifiestos son compatibles con cualquier clúster que tenga Metrics Server.
5. **`imagePullPolicy: Always`:** se republicó el tag `1.0.0` con `baja = 1`; el Deployment fuerza el pull para que el nodo no reutilice la capa anterior.
6. **NodePort en Docker Desktop Windows:** no se publica en `localhost`; se valida mediante `kubectl port-forward --address 0.0.0.0 ... 30080:80`, que es el mismo puente que usa el backend en Docker Compose vía `host.docker.internal:30080`.
7. **Fallos preexistentes ajenos:** la suite del backend da 394 passed y 4 fallos que ya existían antes de la integración (`iniciar_proceso_bonita` tiene la validación de lotes comentada y falta el `set_case_variables`; la matriz de permisos de ofertas consolidadas devuelve 200 a `REPRESENTANTE_ONG`). No se modificaron por estar fuera del alcance.

## Conclusión

Todos los criterios de aceptación de SA1–SA5 quedaron verificados en un clúster real, incluido el
ciclo completo de escalado 1→5→1 y la integración E2E con el backend local, con fallo cerrado (503)
cuando el servicio de prioridad no está disponible.
