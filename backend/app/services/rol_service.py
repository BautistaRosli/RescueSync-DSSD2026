from sqlalchemy.orm import Session

from ..models import Rol

ROLES_INICIALES = [
    "OPERADOR_MUNICIPAL",
    "CENTRO_COORDINADOR",
    "REPRESENTANTE_ONG",
    "DIRECTOR_AUDITOR",
]


def list_roles(db: Session) -> list[Rol]:
    return db.query(Rol).order_by(Rol.id.asc()).all()


def sembrar_roles(db: Session) -> None:
    """Inserta los roles base solo si no existen (idempotente)."""
    for nombre in ROLES_INICIALES:
        existente = db.query(Rol).filter(Rol.nombre == nombre).first()
        if existente is None:
            db.add(Rol(nombre=nombre))
    db.commit()
