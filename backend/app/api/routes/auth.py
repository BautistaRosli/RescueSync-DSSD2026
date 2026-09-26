from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...api.dto import AuthResponseDTO
from ...db import get_db
from ...schemas.usuario import LoginRequest, UsuarioCreate
from ...services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/registro", response_model=AuthResponseDTO, status_code=201)
def registrar_usuario(data: UsuarioCreate, db: Session = Depends(get_db)):
    usuario = auth_service.registrar_usuario(db, data)
    return auth_service.construir_auth_response(usuario)


@router.post("/login", response_model=AuthResponseDTO)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return auth_service.login(db, data)
