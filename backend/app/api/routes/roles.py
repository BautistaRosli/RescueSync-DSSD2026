from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...schemas.rol import RolRead
from ...services import rol_service

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("", response_model=list[RolRead])
def list_roles(db: Session = Depends(get_db)):
    return rol_service.list_roles(db)
