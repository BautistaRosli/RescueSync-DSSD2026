from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencias import requiere_roles
from ...models import Usuario
from ...services.permisos_service import (
    COORDINADOR,
)
from ...database import get_db
from ...dto.usuarios_dto import AuthRespuesta
from ...schemas.usuarios_schema import (
    LoginSolicitud,
    UsuarioCrear,
)
from ...services.usuarios_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/registro", response_model=AuthRespuesta, status_code=201)
def registrar_usuario(
    data: UsuarioCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(COORDINADOR)),
):
    usuario = auth_service.registrar_usuario(db, data)
    return auth_service.construir_auth_response(usuario)


@router.post("/login", response_model=AuthRespuesta)
def login(data: LoginSolicitud, db: Session = Depends(get_db)):
    return auth_service.login(db, data)
