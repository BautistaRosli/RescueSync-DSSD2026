# Despliegue en Kubernetes — RescueSync Prioridad

Servicio stateless `POST /prioridad` (entero 1–10), con `Service` ClusterIP y HPA de **1 a 5 réplicas**.
El `docker-compose.yml` del repo es solo para desarrollo local y **no** forma parte de este despliegue.

## 1. Prerrequisitos

- Docker, `kubectl` apuntando a un clúster (Kind, Minikube, Docker Desktop, EKS, GKE…).
- **Metrics Server** (obligatorio para el HPA).
- Solo si reconstruís la imagen: `docker login` con acceso a DockerHub.

```bash
# Kind (ejemplo)
kind create cluster --name rescuesync

# Metrics Server + ajuste para clústeres locales (Docker Desktop, Kind, Minikube)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl rollout status deployment/metrics-server -n kube-system
kubectl get apiservice v1beta1.metrics.k8s.io   # debe decir Available=True
```

## 2. Imagen

Imagen publicada: `emiliano754/rescuesync-prioridad:1.0.0`.

```bash
# Reconstruir y publicar (opcional)
docker build -t emiliano754/rescuesync-prioridad:1.0.0 ./prioridad-service
docker push emiliano754/rescuesync-prioridad:1.0.0

# Kind sin DockerHub: cargar la imagen local en el nodo
kind load docker-image emiliano754/rescuesync-prioridad:1.0.0 --name rescuesync
```

## 3. Despliegue

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl apply -f k8s/02-secret.yaml
kubectl apply -f k8s/03-deployment.yaml
kubectl apply -f k8s/04-service.yaml
kubectl apply -f k8s/05-hpa.yaml
# Equivalente: kubectl apply -f k8s/
```

> El `Secret` versionado contiene solo un placeholder. En producción:
> `kubectl create secret generic rescuesync-prioridad-secret -n rescuesync --from-literal=API_KEY_INTERNA='<valor-real>'`

## 4. Verificación

```bash
kubectl get pods -n rescuesync                 # Running y Ready 1/1
kubectl get svc -n rescuesync                  # rescuesync-prioridad-svc  ClusterIP  80/TCP
kubectl get hpa -n rescuesync                  # MINPODS=1  MAXPODS=5
kubectl describe hpa -n rescuesync rescuesync-prioridad-hpa   # cpu: X%/70%
kubectl logs -n rescuesync -l app=rescuesync-prioridad --tail=50
```

## 5. Prueba funcional

```bash
kubectl port-forward -n rescuesync svc/rescuesync-prioridad-svc 8080:80
```

En otra terminal:

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/prioridad \
  -H "Content-Type: application/json" \
  -d '{"gravedad":"alta","zona":"norte"}'      # {"prioridad":10,...}
```

Si el puerto 8080 está ocupado (por ejemplo, Bonita local), usá `18080:80`.

## 6. Demostración de escalado

```bash
kubectl run -n rescuesync load --image=busybox --restart=Never -- \
  sh -c "while true; do wget -q -O- http://rescuesync-prioridad-svc/health; done"

kubectl get hpa -n rescuesync -w    # sube hasta 5 réplicas
# Al cortar la carga vuelve a 1 (stabilizationWindowSeconds: 300, ~5 min)
kubectl delete pod -n rescuesync load
```

Si una sola fuente de carga no alcanza, escalá el generador:
`kubectl create deployment load --image=busybox -n rescuesync -- sh -c "while true; do wget -q -O- http://rescuesync-prioridad-svc/health; done"` y `kubectl scale deployment load -n rescuesync --replicas=5`.

## 7. Limpieza

```bash
kubectl delete namespace rescuesync
# Kind: kind delete cluster --name rescuesync
```

## 8. Troubleshooting

| Síntoma | Causa / solución |
| :--- | :--- |
| HPA muestra `<unknown>` | Metrics Server ausente o no listo. Revisar `kubectl get apiservice v1beta1.metrics.k8s.io` y los logs de `metrics-server` en `kube-system`. En clústeres locales con certificados self-signed (Docker Desktop, Kind) aplicar el patch `--kubelet-insecure-tls`. |
| `ImagePullBackOff` | Imagen privada, tag inexistente o sin acceso a DockerHub. Verificar el tag `1.0.0`; en Kind usar `kind load docker-image`. |
| `CrashLoopBackOff` / probes fallando | El proceso no escucha en `8080`. Revisar `kubectl logs` y `kubectl describe pod`. |
| Pod no arranca por permisos | El contenedor corre como UID 1001 y con `readOnlyRootFilesystem`; no debe escribir fuera de `/tmp`. |
| HPA no supera 5 réplicas | Es el máximo definido en `05-hpa.yaml` (`maxReplicas: 5`). |
