from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...dto.usuarios_dto import RolRespuesta
from ...services.usuarios_service import RolService

router = APIRouter(prefix="/roles", tags=["Roles"])

rol_service = RolService()


@router.get("", response_model=list[RolRespuesta])
def list_roles(db: Session = Depends(get_db)):
    return rol_service.listar_roles(db)
