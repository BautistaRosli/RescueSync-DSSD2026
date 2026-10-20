"""Transporte HTTP a Cloud, sin persistencia ni decisiones de autorización."""

import os

import httpx

TIEMPO_LIMITE = 10.0


class AutenticacionAplicacionError(Exception):
    """Cloud no pudo autenticar la aplicación; no contiene detalles remotos."""


def obtener_token_aplicacion() -> str:
    usuario = os.getenv("CLOUD_APP_USUARIO", "")
    password = os.getenv("CLOUD_APP_PASSWORD", "")
    if not usuario.strip() or not password.strip():
        raise AutenticacionAplicacionError() from None
    try:
        respuesta = solicitar("login", usuario, password)
        if respuesta.status_code != 200:
            raise ValueError()
        datos = respuesta.json()
        if (not isinstance(datos, dict) or datos.get("token_type") != "bearer"
                or not isinstance(datos.get("access_token"), str)
                or not datos["access_token"].strip()
                or type(datos.get("expires_in")) is not int or datos["expires_in"] <= 0):
            raise ValueError()
        return datos["access_token"]
    except (httpx.RequestError, httpx.InvalidURL, ValueError, TypeError):
        raise AutenticacionAplicacionError() from None


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
