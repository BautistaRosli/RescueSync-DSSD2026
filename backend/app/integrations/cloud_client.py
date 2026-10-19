"""Transporte HTTP a Cloud, sin persistencia ni decisiones de autorización."""

import os

import httpx

TIEMPO_LIMITE = 10.0


def solicitar(ruta: str, usuario: str, password: str) -> httpx.Response:
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(f"{url}/auth/{ruta}",
                      json={"usuario": usuario, "password": password},
                      timeout=TIEMPO_LIMITE)


def registrar_ong(cuit: str, razon_social: str, email: str, token: str) -> httpx.Response:
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(
        f"{url}/ongs/registro",
        json={"cuit": cuit, "razon_social": razon_social, "email": email},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIEMPO_LIMITE,
    )
