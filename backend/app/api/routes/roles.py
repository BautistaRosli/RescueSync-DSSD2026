from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...domains.usuarios.schemas import RolRespuesta
from ...domains.usuarios.service import RolService

router = APIRouter(prefix="/roles", tags=["Roles"])

rol_service = RolService()


@router.get("", response_model=list[RolRespuesta])
def list_roles(db: Session = Depends(get_db)):
    return rol_service.listar_roles(db)
