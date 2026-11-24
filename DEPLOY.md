# Despliegue Kubernetes — RescueSync Prioridad
Guía rápida para ejecutar el microservicio `prioridad-service` en Kubernetes.
El servicio expone `POST /prioridad`, devuelve una prioridad de **1 a 10** y se publica mediante un `NodePort` en el puerto `30080`. El HPA escala de 1 a 5 réplicas.

## 1. Requisitos

- Docker y `kubectl` configurado para un clúster (Docker Desktop, Kind, Minikube o cloud).
- Metrics Server para que funcione el HPA.
- Acceso a Docker Hub solo si se reconstruye la imagen.

Comprobar el contexto:

```bash
kubectl config current-context
kubectl get nodes
```

Instalar Metrics Server si el clúster todavía no lo tiene:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Necesario en Docker Desktop o Kind si el kubelet usa certificados self-signed:
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

kubectl rollout status deployment/metrics-server -n kube-system
kubectl get apiservice v1beta1.metrics.k8s.io
```

## 2. Imagen y secreto

La imagen usada por el Deployment es `emiliano754/rescuesync-prioridad:1.0.0` con `imagePullPolicy: Always`.

Crear el secreto real antes de desplegar (el manifiesto contiene un placeholder):

```bash
kubectl create namespace rescuesync --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic rescuesync-prioridad-secret -n rescuesync \
  --from-literal=API_KEY_INTERNA='<valor-real>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 3. Desplegar

Desde la raíz del repositorio:

```bash
kubectl apply -f k8s/
kubectl rollout status deployment/rescuesync-prioridad -n rescuesync --timeout=120s
```

En Docker Desktop Windows, este script aplica los manifiestos, espera el rollout y mantiene un puente local durante 24 horas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-prioridad.ps1
```

Verificar:

```bash
kubectl get pods -n rescuesync
kubectl get svc -n rescuesync
kubectl get hpa -n rescuesync
```

Resultado esperado: Pod `Running` y `Ready 1/1`, Service `80:30080/TCP` y HPA con mínimo 1 y máximo 5 réplicas.

## 4. Probar el servicio

En Kind, Minikube o cloud usar `http://<IP-del-nodo>:30080`.

En Docker Desktop Windows, iniciar el puente:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\port-forward-prioridad.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\port-forward-prioridad.ps1 -Status
# Para detenerlo:
powershell -ExecutionPolicy Bypass -File .\scripts\port-forward-prioridad.ps1 -Stop
```

Healthcheck y prueba de prioridades. El servicio acepta `baja`, `media`, `alta` y `critica`.

```bash
curl http://localhost:30080/health
curl -X POST http://localhost:30080/prioridad \
  -H "Content-Type: application/json" \
  -d '{"gravedad":"critica","zona":"norte"}'
```

## 5. Conectar el backend local

Configurar `PRIORIDAD_SERVICE_URL` según dónde corre el backend:

| Backend | Valor |
|---|---|
| Ejecutado en el host | `http://localhost:30080` |
| Ejecutado en Docker Compose | `http://host.docker.internal:30080` |

En Docker Compose ya está configurado. Para levantar el entorno:

```bash
docker compose up -d --build
```

El backend consulta prioridad antes de guardar una emergencia. Si el servicio no responde en 3 segundos, devuelve `503` y no persiste la emergencia.

## 6. Escalado opcional

```bash
kubectl run -n rescuesync load --image=fortio/fortio:latest --restart=Never -- \
  load -c 30 -qps 0 -t 300s http://rescuesync-prioridad-svc/health
kubectl get hpa -n rescuesync -w
kubectl delete pod -n rescuesync load
```

## 7. Problemas frecuentes y limpieza

- **HPA en `<unknown>`:** Metrics Server no está listo. Revisar `kubectl get apiservice v1beta1.metrics.k8s.io`.
- **`ImagePullBackOff`:** comprobar el tag `1.0.0`, `docker login` y `docker push`.
- **`localhost:30080` no responde:** iniciar `port-forward-prioridad.ps1` en Docker Desktop.
- **Backend devuelve `503`:** verificar `PRIORIDAD_SERVICE_URL`, el Service y el endpoint `/health`.

Para eliminar todo el despliegue:

```bash
kubectl delete namespace rescuesync
```
