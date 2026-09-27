from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas.usuarios import (
    AuthRespuesta,
    LoginSolicitud,
    UsuarioCrear,
)
from ...services.usuarios import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/registro", response_model=AuthRespuesta, status_code=201)
def registrar_usuario(data: UsuarioCrear, db: Session = Depends(get_db)):
    usuario = auth_service.registrar_usuario(db, data)
    return auth_service.construir_auth_response(usuario)


@router.post("/login", response_model=AuthRespuesta)
def login(data: LoginSolicitud, db: Session = Depends(get_db)):
    return auth_service.login(db, data)
