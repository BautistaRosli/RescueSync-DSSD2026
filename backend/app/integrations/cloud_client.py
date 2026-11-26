"""Transporte HTTP a Cloud, sin persistencia ni decisiones de autorización."""

import os
from threading import Lock
from time import monotonic

import httpx

TIEMPO_LIMITE = 10.0
_bloqueo_token_aplicacion = Lock() # Protege la sesión de la aplicación y su token de acceso.
_sesion_aplicacion: tuple[tuple[str, str, str], str, float] | None = None 


class AutenticacionAplicacionError(Exception):
    """Cloud no pudo autenticar la aplicación; no contiene detalles remotos."""


def obtener_token_aplicacion() -> str:
    """Reutiliza la sesión del proceso y renueva al operar cerca del vencimiento."""
    # Guarda la sesión de la aplicación en memoria para no tener que pedir un token cada vez que se hace una solicitud a Cloud:
    # Es una tupla de tres elementos: (configuración, token, tiempo_de_renovación), donde:
    # - configuración: una tupla de tres elementos (url_base, usuario, password)
    # - token: el token de acceso actual
    # - tiempo_de_renovación: el tiempo (monotonic) en que se debe renovar el token (antes de que expire)
    global _sesion_aplicacion 


    # Agarra las credenciales de la aplicación desde las variables de entorno.
    usuario = os.getenv("CLOUD_APP_USUARIO", "")
    password = os.getenv("CLOUD_APP_PASSWORD", "")
    if not usuario.strip() or not password.strip():
        raise AutenticacionAplicacionError() from None
    
    configuracion = (os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/"), usuario, password)
    with _bloqueo_token_aplicacion:
        
        # Si ya tenemos un token válido y NO ha llegado el momento de renovarlo, lo devolvemos.
        inicio = monotonic()
        if (_sesion_aplicacion is not None
                and _sesion_aplicacion[0] == configuracion
                and inicio < _sesion_aplicacion[2]):
            return _sesion_aplicacion[1]
        
        # Sino pedimos uno nuevo a Cloud.
        try:
            # Peticion y Validación de la respuesta.
            respuesta = solicitar("login", usuario, password)
            if respuesta.status_code != 200:
                raise ValueError()
            datos = respuesta.json()
            if (not isinstance(datos, dict) or datos.get("token_type") != "bearer"
                    or not isinstance(datos.get("access_token"), str)
                    or not datos["access_token"].strip()
                    or type(datos.get("expires_in")) is not int or datos["expires_in"] <= 0):
                raise ValueError()
            
            # Definimos el tiempo de renovación del token, que es un poco antes de que expire.
            margen = min(30.0, datos["expires_in"] * 0.1)
            renovar_en = inicio + datos["expires_in"] - margen
            _sesion_aplicacion = (configuracion, datos["access_token"], renovar_en)
            
            # Devolvemos el token de acceso.
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


def obtener_ong(ong_id: int, token: str) -> httpx.Response:
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.get(
        f"{url}/ongs/{ong_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIEMPO_LIMITE,
    )


def listar_items(token: str) -> httpx.Response:
    """Obtiene el catálogo nacional de recursos de Cloud."""
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.get(
        f"{url}/items",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIEMPO_LIMITE,
    )


def crear_item(nombre: str, descripcion: str | None, token: str) -> httpx.Response:
    """Crea un recurso en el catálogo nacional de Cloud."""
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(
        f"{url}/items",
        json={"nombre": nombre, "descripcion": descripcion},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIEMPO_LIMITE,
    )


def bloquear_recursos(solicitud: dict, token: str) -> httpx.Response:
    """Envía una solicitud para bloquear recursos en Cloud."""
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(
        f"{url}/recursos/bloquear", json=solicitud,
        headers={"Authorization": f"Bearer {token}"}, timeout=TIEMPO_LIMITE,
    )


def liberar_emergencia(emergencia_id: int, token: str) -> httpx.Response:
    """Libera los compromisos activos de la emergencia en Cloud."""
    url = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002").rstrip("/")
    return httpx.post(
        f"{url}/emergencias/{emergencia_id}/liberar",
        headers={"Authorization": f"Bearer {token}"}, timeout=TIEMPO_LIMITE,
    )
