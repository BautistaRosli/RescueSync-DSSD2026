# Validación — RescueSync Prioridad en Kubernetes

**Fecha:** 2026-11-19
**Entorno:** Windows 11 · Docker 29.5.2 · Kubernetes de Docker Desktop v1.34.3 (nodo `desktop-control-plane`) · Metrics Server v0.9.1
**Imagen:** `emiliano754/rescuesync-prioridad:1.0.0` · digest `sha256:0cbdbb84b34f5e6aeab4ef310beb5ebcd667968eff1540c888074deb29087212`

## Resultados

| Check | Comando | Esperado | Obtenido | Estado |
| :--- | :--- | :--- | :--- | :--- |
| Tests unitarios | `pytest -q prioridad-service` | 100 % verde | 27 passed, 1 warning (deprecación de anyio/starlette) | ✅ |
| Build de imagen | `docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./prioridad-service` | Sin errores | Build OK; HEALTHCHECK `healthy` | ✅ |
| Tamaño de imagen | `docker image inspect ...` | < 300 MB | 54.1 MiB (56.770.618 bytes) | ✅ |
| Usuario no root | `docker inspect --format "{{.Config.User}}" ...` | ≠ root | `appuser` (UID/GID 1001) | ✅ |
| Salud local | `GET /health`, `GET /ready` | 200 | 200 `{"status":"ok"}` / `{"status":"ready"}` | ✅ |
| Prioridad local | `POST /prioridad` `{"gravedad":"alta","zona":"norte"}` | entero en [1,10] | 200, `prioridad: 10` | ✅ |
| Validación 422 | `gravedad: "critica"` | 422 | 422 | ✅ |
| Validación 400 | `zona: "   "` | 400 | 400 `La zona no puede estar vacía` | ✅ |
| Imagen pública | Docker Hub API | pública, tag `1.0.0` | `private=False`, push de `1.0.0` y `latest` OK | ✅ |
| Manifiestos | `kubectl apply --dry-run=client -f k8s/` | Sin errores | 6 recursos creados (dry run) | ✅ |
| Esquema YAML | `kubeconform -strict k8s/` | 0 inválidos | 6/6 válidos | ✅ |
| Despliegue | `kubectl apply -f k8s/` | Sin errores | 6 recursos creados | ✅ |
| Pods | `kubectl get pods -n rescuesync` | Running y Ready | `1/1 Running`, 0 restarts | ✅ |
| Service | `kubectl get svc -n rescuesync` | ClusterIP 80→8080 | `rescuesync-prioridad-svc` 80/TCP | ✅ |
| HPA límites | `kubectl get hpa -n rescuesync` | MINPODS=1, MAXPODS=5 | `1` y `5` | ✅ |
| HPA métricas | `kubectl describe hpa` | cpu real, no `<unknown>` | `cpu: 4%/70%`, `memory: 29%/80%` | ✅ |
| Prueba vía Service | `port-forward svc/... 18080:80` + `curl` | entero en [1,10] | `{"prioridad":10,...}`, HTTP 200 | ✅ |
| Escalado bajo carga | `fortio load -c 30 -t 300s` | sube hasta 5 y no más | 1→2→3→4→5; se mantuvo en 5 | ✅ |
| Descenso al cesar carga | observación del HPA | vuelve a 1 | 5→2→1 en ~10 min (stabilization 300 s) | ✅ |
| Secret sin credenciales reales | `kubectl get secret ... -o jsonpath` | solo placeholder | `API_KEY_INTERNA=cambiar-en-produccion` | ✅ |
| `DEPLOY.md` | longitud del documento | ≤ 2 carillas | 81 líneas, compacto (~2 páginas) | ✅ |
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

## Evidencia final

```
$ kubectl get deploy,hpa -n rescuesync
deployment.apps/rescuesync-prioridad   1/1   1   1
rescuesync-prioridad-hpa   cpu: 4%/70%, memory: 29%/80%   1   5   1

$ kubectl logs -n rescuesync -l app=rescuesync-prioridad --tail=1
{"timestamp":"...","level":"info","logger":"prioridad","message":"request",
 "method":"GET","path":"/health","status":200,"duration_ms":0.68}
```

## Desviaciones respecto de `tasks.md`

1. **Ubicación del código:** se usó `prioridad-service/` en la raíz (no `backend/`) para no pisar el backend existente del proyecto. El `Dockerfile` y los manifiestos referencian esa ruta.
2. **`pytest.ini` propio** en `prioridad-service/`: el `pytest.ini` raíz fija `testpaths = backend/tests`; el archivo local aísla los tests del servicio y define `pythonpath = .`.
3. **Metrics Server:** en clústeres locales con certificados self-signed (Docker Desktop, Kind) requiere el argumento `--kubelet-insecure-tls`. Sin él, el HPA queda en `<unknown>`. Documentado en `DEPLOY.md`.
4. **Clúster validado:** Docker Desktop en lugar de Kind (Kind no estaba instalado al momento de validar). Los manifiestos son compatibles con cualquier clúster que tenga Metrics Server.
5. **`docker push`:** se publicaron `1.0.0` y `latest` en Docker Hub; la política del Deployment usa `IfNotPresent` y el tag versionado.

## Conclusión

Todos los criterios de aceptación de SA1–SA5 quedaron verificados en un clúster real, incluido el ciclo completo de escalado 1→5→1.
