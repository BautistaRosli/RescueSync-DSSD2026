"""Transporte HTTP de credenciales a Cloud, sin persistencia ni autorización."""

import os

import httpx

TIEMPO_LIMITE = 10.0


def solicitar(ruta: str, usuario: str, password: str) -> httpx.Response:
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(f"{url}/auth/{ruta}",
                      json={"usuario": usuario, "password": password},
                      timeout=TIEMPO_LIMITE)
