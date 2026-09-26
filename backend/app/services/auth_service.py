import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..api.dto import AuthResponseDTO
from ..models import Rol, Usuario
from ..schemas.usuario import LoginRequest, UsuarioCreate, UsuarioRead

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


def generar_token(usuario: Usuario) -> str:
    emitido = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario.id),
        "rol": usuario.rol.nombre,
        "rol_id": usuario.rol_id,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=expiracion_minutes()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def construir_auth_response(usuario: Usuario) -> AuthResponseDTO:
    return AuthResponseDTO(
        access_token=generar_token(usuario),
        token_type="bearer",
        rol=usuario.rol.nombre,
        usuario=UsuarioRead.model_validate(usuario),
    )


def registrar_usuario(db: Session, data: UsuarioCreate) -> Usuario:
    existente = (
        db.query(Usuario).filter(Usuario.email == data.email).first()
    )
    if existente is not None:
        raise HTTPException(
            status_code=409, detail="El email ya está registrado"
        )

    rol = db.get(Rol, data.rol_id)
    if rol is None:
        raise HTTPException(
            status_code=404, detail="Rol no encontrado"
        )

    usuario = Usuario(
        email=data.email,
        password_hash=hashear_password(data.password),
        nombre=data.nombre,
        apellido=data.apellido,
        rol_id=rol.id,
        municipio_id=data.municipio_id,
        organizacion_id=data.organizacion_id,
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def login(db: Session, data: LoginRequest) -> AuthResponseDTO:
    usuario = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.email == data.email)
        .first()
    )

    if usuario is None or not verificar_password(
        data.password, usuario.password_hash
    ):
        raise HTTPException(
            status_code=401, detail="Credenciales inválidas"
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=403, detail="El usuario está inactivo"
        )

    return construir_auth_response(usuario)
