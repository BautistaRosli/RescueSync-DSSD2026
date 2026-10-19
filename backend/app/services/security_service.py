import os

import bcrypt
import jwt
from fastapi import HTTPException

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Debe configurar JWT_SECRET antes de iniciar la API")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "rescuesync-cloud")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "rescuesync-backend")


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


def validar_token_cloud(token: str) -> dict:
    """Valida la identidad remota; los permisos siempre salen de la base local."""
    datos = jwt.decode(
        token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
        options={"require": ["exp", "iat", "sub", "usuario", "iss", "aud"]},
    )
    if (not isinstance(datos["sub"], str) or not datos["sub"].strip()
            or not isinstance(datos["usuario"], str) or not datos["usuario"].strip()
            or type(datos["iat"]) is not int or type(datos["exp"]) is not int):
        raise jwt.InvalidTokenError("Identidad Cloud inválida")
    return datos
