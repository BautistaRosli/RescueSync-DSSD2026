"""Dependencias compartidas de autenticación y autorización."""

import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..repositories import UsuarioRepository
from ..services.security_service import JWT_ALGORITHM, JWT_SECRET
from ..services.permisos_service import denegar

portador = HTTPBearer(auto_error=False)


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(portador),
    db: Session = Depends(get_db),
) -> Usuario:
    error = HTTPException(
        401, "Se requiere un token válido", headers={"WWW-Authenticate": "Bearer"}
    )
    if credenciales is None:
        raise error
    try:
        datos = jwt.decode(
            credenciales.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        identificador = int(datos["sub"])
        if identificador <= 0:
            raise ValueError()
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise error from None
    usuario = UsuarioRepository().obtener_por_id(db, identificador)
    if usuario is None:
        raise error
    if not usuario.activo:
        raise HTTPException(403, "El usuario está inactivo")
    return usuario


def requiere_roles(*roles: str):
    def autorizar(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol is None or usuario.rol.nombre not in roles:
            denegar()
        return usuario
    return autorizar


def solo_development() -> None:
    if os.getenv("APP_ENV") != "development":
        raise HTTPException(404, "Diagnóstico no disponible")
