# syntax=docker/dockerfile:1

# ---------- Etapa 1: construcción de dependencias ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# ---------- Etapa 2: runtime mínimo ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    PYTHONPATH=/home/appuser/.local/lib/python3.12/site-packages \
    PATH=/home/appuser/.local/bin:$PATH

RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid 1001 --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /root/.local /home/appuser/.local
COPY app /app/app

WORKDIR /app

RUN chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
