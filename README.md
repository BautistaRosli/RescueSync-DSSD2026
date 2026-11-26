# RescueSync - DSSD 2026

Proyecto desarrollado para la cursada de DSSD 2026.

---

### Stack

* **Backend:** FastAPI (Python) + SQLAlchemy + HTTPX para hablarle a la API de Bonita BPM.
* **Frontend:** React + TypeScript montado sobre Vite, usando Bun como package manager y Tailwind CSS para los estilos.
* **Base de datos:** PostgreSQL 16.
* **Infraestructura:** Docker & Docker Compose en WSL.

---

### Cómo correr el proyecto

Solo se necesita tener instalado Docker (con Docker Desktop o Docker Engine en WSL) y clonar el repo.

1. **Configurar el entorno de desarrollo:** copiar `backend/.env.example` a
   `backend/.env` (sin sobrescribirlo si ya existe), mantener
   `APP_ENV=development` y completar `JWT_SECRET` con un secreto aleatorio propio.
   Se puede generar con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   El backend requiere este secreto para arrancar; no publicar el archivo `.env`.

2. **Levantar todos los contenedores:**
   ```bash
   docker compose up --build
   ```

3. **Acceder a los servicios:**
   * Frontend: [http://localhost:5173](http://localhost:5173)
   * Backend / Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   * Base de datos: `localhost:5432`
   * Api sistema nacional / Swagger Docs [http://localhost:8001/docs]

4. **Apagar los servicios:**
   ```bash 
   docker compose down
   ```
   *(Si además querés borrar la persistencia de la BD, agregá `-v`)*

### Vinculación nacional de las ONG de demostración

En `development`, el backend crea o reutiliza las filas locales de ONU y UNICEF. Para vincularlas automáticamente, configurar `CLOUD_APP_USUARIO` y `CLOUD_APP_PASSWORD` en `backend/.env`. Se usan los CUIT de demostración. Si Cloud no puede confirmar la identidad, la precarga automática informa el error y el arranque se interrumpe.

- Para usar otro CUIT, configurar `CLOUD_ONU_CUIT` o `CLOUD_UNICEF_CUIT`. Si Cloud informa que la ONG ya existe, el backend puede recuperar la vinculación cuando recibe un ID y verifica que la ficha coincide en CUIT, razón social y email.
- Si ya se conoce el ID nacional, configurar `CLOUD_ONU_ONG_ID` o `CLOUD_UNICEF_ONG_ID` y el CUIT correspondiente. Cuando se proporciona una configuración explícita y la ficha no se puede verificar, la organización queda local y la vinculación puede reintentarse en el próximo arranque. Una vinculación existente se conserva.
- Sin credenciales ni configuración nacional, la precarga de estas ONG conserva sólo los registros locales. El catálogo de recursos de demostración usa su propia consulta a Cloud.

Con Docker Compose, `CLOUD_API_URL` se toma del entorno de Compose o del `.env` situado junto a `docker-compose.yml`. Después de cambiar la configuración, ejecutar `docker compose up -d --force-recreate --no-deps backend`. Los IDs confirmados se pueden consultar en la base municipal.

```sql
SELECT o.nombre, n.ong_id
FROM organizaciones AS o
JOIN organizaciones_cloud AS n ON n.organizacion_id = o.id
WHERE o.nombre IN ('Organización de las Naciones Unidas', 'UNICEF');
```

### Adjudicar ofertas desde el Centro Coordinador

En **Esperando adjudicación**, abrir la emergencia para ver las ofertas.

- **Adjudicar** incorpora una oferta a la selección. Se pueden marcar otras de la misma emergencia. **Confirmar selección** envía a la tarea **Seleccionar oferta** de Bonita los pares de oferta y lote adjudicados. La emergencia pasa a **En proceso** cuando Bonita acepta la selección.
- **Adjudicar solo esta oferta** adjudica una única oferta y pasa la emergencia a **En proceso** de inmediato. Desde esa pestaña se puede enviar la adjudicación a Bonita con **Confirmar selección**.

Si falla la confirmación, las adjudicaciones se conservan. Si el envío ya comenzó y su resultado es incierto, se mantiene el mismo conjunto de ofertas. Volver a pulsar **Confirmar selección** permite completar la tarea o reconocer la selección que Bonita ya recibió.

En la API, `POST /api/v1/ofertas/{id}/adjudicar` mantiene la adjudicación individual. Con `?para_seleccion=true` prepara la oferta para el conjunto. La confirmación se realiza con `POST /api/v1/emergencias/{id}/confirmar-seleccion`. Las tres llamadas se envían sin cuerpo.

### Servicio de prioridad en Kubernetes

El microservicio `rescuesync-prioridad` (stateless, `POST /prioridad`, HPA de 1 a 5
réplicas) se despliega con los manifiestos de `k8s/`. Los pasos completos
(prerrequisitos, Metrics Server, despliegue, pruebas y escalado) están en
[`DEPLOY.md`](DEPLOY.md).

```bash
kubectl apply -f k8s/
kubectl get pods,hpa -n rescuesync
```

El `docker-compose.yml` es únicamente para desarrollo local y no forma parte del
entregable de Kubernetes.

### Autenticación y permisos de la API

Las operaciones de negocio requieren `Authorization: Bearer <token>`. El login
(`POST /api/v1/auth/login`), el catálogo de roles y la respuesta de salud son
públicos. La API verifica el JWT y consulta el usuario activo, su rol y su
organización actuales en la base de datos.

| Rol | Alcance |
| :--- | :--- |
| `OPERADOR_MUNICIPAL` | Crea emergencias y consulta las no publicadas y sus lotes. |
| `CENTRO_COORDINADOR` | Consulta todos los recursos; administra emergencias, lotes, organizaciones y altas de usuarios. |
| `REPRESENTANTE_ONG` | Consulta emergencias publicadas y sus lotes; consulta su organización y crea o modifica ofertas de su propia organización. |
| `DIRECTOR_AUDITOR` | Consulta todos los recursos de negocio, sin escrituras. |

`POST /api/v1/auth/registro` requiere un coordinador autenticado. Para crear un
representante de ONG debe asignarse una organización existente. El primer
coordinador debe estar previamente provisionado en la base de datos: no hay
registro público ni creación automática de cuentas privilegiadas. La respuesta
del alta corresponde al usuario creado y no debe reemplazar la sesión del
coordinador.

Los diagnósticos `POST /api/v1/bonita/test-login` y
`POST /api/v1/bonita/test-variables` requieren coordinador y sólo están disponibles
con `APP_ENV=development`; fuera de ese entorno responden `404`. El diagnóstico
de login dejó de usar `GET` porque inicia una sesión remota.

La ausencia de credenciales válidas devuelve `401`; un usuario inactivo, un rol
no autorizado o el acceso a datos fuera de su alcance devuelve `403`. Los filtros
de consulta no amplían los permisos. Las reglas de negocio existentes siguen
aplicándose aunque el usuario tenga el rol requerido.

### Usuarios default
municipio@municipio.com
coordinador@coordinador.com
ong@ong.com
auditor@auditor.com
