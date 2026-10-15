from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...dto.usuarios_dto import AuthRespuesta, UsuarioRespuesta
from ...models import Usuario
from ...schemas.usuarios_schema import (
    LoginSolicitud,
    UsuarioCrear,
)
from ...services.usuarios_service import AuthService
from ..dependencias import usuario_actual

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/registro", response_model=AuthRespuesta, status_code=201)
def registrar_usuario(data: UsuarioCrear, db: Session = Depends(get_db)):
    nuevo_usuario = auth_service.registrar_usuario(db, data)
    return auth_service.construir_auth_response(nuevo_usuario)


@router.post("/login", response_model=AuthRespuesta)
def login(data: LoginSolicitud, db: Session = Depends(get_db)):
    return auth_service.login(db, data)


@router.get("/me", response_model=UsuarioRespuesta)
def obtener_usuario_actual(usuario: Usuario = Depends(usuario_actual)):
    return auth_service.usuario_actual(usuario)
