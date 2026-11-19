# prioridad-service

Microservicio stateless de RescueSync que calcula la prioridad de un incidente
a partir de su gravedad y su zona. La prioridad depende **solo** de esos dos
datos, nunca del cliente que realiza la solicitud.

## Stack

- Python 3.12
- FastAPI + Uvicorn
- Tests con pytest y httpx

## Endpoints

| Método | Path | Descripción |
| :--- | :--- | :--- |
| `GET` | `/health` | Sonda de vida → `{"status": "ok"}` |
| `GET` | `/ready` | Sonda de disponibilidad → `{"status": "ready"}` |
| `POST` | `/prioridad` | Calcula la prioridad de un incidente |

### `POST /prioridad`

Entrada:

```json
{"gravedad": "alta", "zona": "norte"}
```

Salida `200`:

```json
{
  "prioridad": 10,
  "gravedad": "alta",
  "zona": "norte",
  "timestamp": "2026-11-19T12:00:00+00:00"
}
```

Errores:

- `422`: payload inválido, campo faltante o `gravedad` fuera de `alta|media|baja`.
- `400`: `zona` vacía o compuesta solo por espacios.

## Ejecución local

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Variables de entorno

| Variable | Default | Descripción |
| :--- | :--- | :--- |
| `PORT` | `8080` | Puerto de escucha (al ejecutar `python -m app.main`). |
| `LOG_LEVEL` | `info` | Nivel de los logs JSON emitidos a stdout. |

Cada request genera una línea JSON con `method`, `path`, `status` y `duration_ms`.

## Docker

```bash
docker build -t emiliano754/rescuesync-prioridad:1.0.0 .
docker run -d --name rescuesync-prioridad -p 18080:8080 emiliano754/rescuesync-prioridad:1.0.0
curl.exe http://localhost:18080/health
```

La imagen corre como usuario no root `appuser` (UID 1001) y expone el puerto `8080`.
