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

1. **Levantar todos los contenedores:**
   ```bash
   docker compose up --build
   ```

2. **Acceder a los servicios:**
   * Frontend: [http://localhost:5173](http://localhost:5173)
   * Backend / Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   * Base de datos: `localhost:5432`

3. **Apagar los servicios:**
   ```bash
   docker compose down
   ```
   *(Si además querés borrar la persistencia de la BD, agregá `-v`)*