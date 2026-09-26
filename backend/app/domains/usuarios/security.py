import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

JWT_SECRET = os.getenv(
    "JWT_SECRET", "rescuesync-dev-secret-cambiar-en-produccion-2026"
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES_POR_DEFECTO = 60


def expiracion_minutes() -> int:
    try:
        return int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
    except ValueError:
        return JWT_EXPIRATION_MINUTES_POR_DEFECTO


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
    payload = {
        "sub": str(usuario_id),
        "rol": rol_nombre,
        "rol_id": rol_id,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=expiracion_minutes()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
