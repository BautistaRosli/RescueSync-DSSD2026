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

En `development`, el backend crea o reutiliza las filas locales de ONU y UNICEF. Para vincularlas con Cloud, completar en `backend/.env` el CUIT de cada una en `CLOUD_ONU_CUIT` o `CLOUD_UNICEF_CUIT`, además de las credenciales de aplicación de Cloud. Con Docker Compose, la variable `CLOUD_API_URL` se toma del entorno de Compose o del `.env` situado junto a `docker-compose.yml`.

- Si la ONG ya existe en Cloud, completar también `CLOUD_ONU_ONG_ID` o `CLOUD_UNICEF_ONG_ID` con su ID nacional. El backend consulta la ficha y comprueba su identidad antes de vincularla.
- Si necesita el alta nacional, dejar vacío su ID y completar sólo su CUIT. Cuando Cloud confirma el alta, el backend guarda el ID que recibió. Si Cloud informa que el CUIT ya existe, se necesita el ID de esa ficha.

Después de actualizar la configuración, ejecutar `docker compose up -d --force-recreate --no-deps backend`. La precarga también completa las vinculaciones pendientes de organizaciones existentes. Para configurar otra instalación que use el mismo Cloud, se pueden consultar los IDs confirmados en la base municipal ya vinculada.

```sql
SELECT o.nombre, n.ong_id
FROM organizaciones AS o
JOIN organizaciones_cloud AS n ON n.organizacion_id = o.id
WHERE o.nombre IN ('Organización de las Naciones Unidas', 'UNICEF');
```

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