# Despliegue en Kubernetes — RescueSync Prioridad

Microservicio stateless `POST /prioridad` (entero **1–10**), un único `Service` **NodePort 30080**
y **HPA de 1 a 5 réplicas**. El resto de RescueSync (`frontend/`, `backend/`, PostgreSQL y Bonita)
sigue corriendo local como hasta ahora; `docker-compose.yml` es solo para desarrollo y **no** es
parte de este entregable.

## 1. Prerrequisitos

- Docker, `kubectl` apuntando a un clúster (Kind, Minikube, Docker Desktop, EKS, GKE…).
- **Metrics Server** (obligatorio para el HPA).
- Solo si reconstruís la imagen: `docker login` con acceso a Docker Hub.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Clústeres locales con certificados self-signed (Docker Desktop, Kind):
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl rollout status deployment/metrics-server -n kube-system
kubectl get apiservice v1beta1.metrics.k8s.io   # Available=True
```

## 2. Imagen en Docker Hub

Imagen publicada: `emiliano754/rescuesync-prioridad:1.0.0`.

```bash
docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./prioridad-service
docker push emiliano754/rescuesync-prioridad:1.0.0
```

## 3. Despliegue y verificación

```bash
kubectl apply -f k8s/
kubectl get pods -n rescuesync          # Running y Ready 1/1
kubectl get svc -n rescuesync           # NodePort 80:30080/TCP
kubectl get hpa -n rescuesync           # MINPODS=1  MAXPODS=5
kubectl describe hpa -n rescuesync rescuesync-prioridad-hpa   # cpu: X%/70%
```

> El `Secret` versionado contiene solo un placeholder. En producción:
> `kubectl create secret generic rescuesync-prioridad-secret -n rescuesync --from-literal=API_KEY_INTERNA='<valor-real>'`

## 4. Acceso local y prueba funcional

**Kind / Minikube / cloud:** `http://<IP-del-nodo>:30080`.

**Docker Desktop en Windows:** el NodePort no se publica automáticamente en `localhost`; usar el
puente (dejar la terminal abierta):

```bash
kubectl port-forward --address 0.0.0.0 -n rescuesync svc/rescuesync-prioridad-svc 30080:80
```

En otra terminal:

```bash
curl http://localhost:30080/health
curl -X POST http://localhost:30080/prioridad \
  -H "Content-Type: application/json" -d '{"gravedad":"baja","zona":"centro"}'   # prioridad 1
curl -X POST http://localhost:30080/prioridad \
  -H "Content-Type: application/json" -d '{"gravedad":"alta","zona":"norte"}'    # prioridad 10
```

## 6. Integración con el backend local

El backend consulta el servicio **antes** de persistir la emergencia:

- Backend nativo: `PRIORIDAD_SERVICE_URL=http://localhost:30080`.
- Backend en Docker Compose: `http://host.docker.internal:30080` (ya definido en `docker-compose.yml`).
- `critica` se envía como `alta`. Si el servicio no responde en 3 s, el backend devuelve **503** y
  no registra la emergencia.

```bash
docker compose up -d --build
# Luego registrar la emergencia desde el frontend; la confirmación muestra la prioridad 1–10.
```

## 7. Demostración de escalado

```bash
kubectl run -n rescuesync load --image=fortio/fortio:latest --restart=Never -- \
  load -c 30 -qps 0 -t 300s http://rescuesync-prioridad-svc/health

kubectl get hpa -n rescuesync -w    # 1 → 5 réplicas y se mantiene en 5
kubectl delete pod -n rescuesync load
# Al cortar la carga vuelve a 1 (stabilizationWindowSeconds: 300, ~10 min)
```

## 7. Limpieza

```bash
kubectl delete namespace rescuesync
```

## 8. Troubleshooting

| Síntoma | Causa / solución |
| :--- | :--- |
| HPA en `<unknown>` | Metrics Server ausente o no listo. Revisar `kubectl get apiservice v1beta1.metrics.k8s.io`; en local aplicar `--kubelet-insecure-tls`. |
| `ImagePullBackOff` | Imagen/tag inexistente o sin acceso a Docker Hub. Verificar `1.0.0` y `docker push`. |
| `localhost:30080` no responde | En Docker Desktop Windows usar el `kubectl port-forward` de la sección 5. |
| Backend devuelve 503 al registrar | El servicio de prioridad no es alcanzable en `PRIORIDAD_SERVICE_URL` o tardó más de 3 s. |
