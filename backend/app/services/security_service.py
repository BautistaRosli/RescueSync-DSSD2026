import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Debe configurar JWT_SECRET antes de iniciar la API")
JWT_ALGORITHM = "HS256"
# Namespace propio: la configuración heredada de Cloud no define sesiones locales.
JWT_ISSUER = "rescuesync-local"
JWT_AUDIENCE = "rescuesync-local-api"


def expiracion_minutes() -> int:
    try:
        minutos = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
        return minutos if minutos > 0 else 60
    except ValueError:
        return 60


def hashear_password(password: str) -> str:
    try:
        hash_bytes = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="La contraseña supera el máximo de 72 bytes permitido",
        ) from exc
    return hash_bytes.decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (TypeError, ValueError):
        return False


def generar_token(usuario_id: int, rol_id: int, rol_nombre: str) -> str:
    emitido = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(usuario_id), "rol_id": rol_id, "rol": rol_nombre,
        "iat": emitido, "exp": emitido + timedelta(minutes=expiracion_minutes()),
        "iss": JWT_ISSUER, "aud": JWT_AUDIENCE,
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)


def validar_token_local(token: str) -> dict:
    """Valida la sesión local; los permisos se consultan en la base de datos."""
    datos = jwt.decode(
        token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
    )
    if (not isinstance(datos["sub"], str)
            or re.fullmatch(r"[1-9][0-9]{0,9}", datos["sub"]) is None
            or int(datos["sub"]) > 2147483647
            or type(datos["iat"]) is not int or type(datos["exp"]) is not int
            or datos["exp"] <= datos["iat"]):
        raise jwt.InvalidTokenError("Identidad local inválida")
    return datos
