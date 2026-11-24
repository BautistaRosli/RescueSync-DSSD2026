from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from ..models import Organizacion, OrganizacionCloud, Rol, Usuario


class OrganizacionRepository:
    def bloquear_precarga(self, db: Session, clave: int) -> None:
        """Serializa una creación local o la comprobación final de referencias."""
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(2026, :clave)"), {"clave": clave})

    def buscar_precarga(self, db: Session, nombre: str) -> list[Organizacion]:
        return db.query(Organizacion).filter_by(nombre=nombre).order_by(Organizacion.id).all()

    def obtener_para_vincular(self, db: Session, organizacion_id: int) -> Organizacion:
        return (db.query(Organizacion).filter_by(id=organizacion_id)
                .populate_existing().with_for_update().one())

    def referencia_nacional_ocupada(self, db: Session, ong_id: int,
                                   organizacion_id: int) -> bool:
        return (db.query(OrganizacionCloud).filter(
            OrganizacionCloud.ong_id == ong_id,
            OrganizacionCloud.organizacion_id != organizacion_id).first() is not None)

    def obtener_por_id(
        self, db: Session, organizacion_id: int
    ) -> Optional[Organizacion]:
        return db.get(Organizacion, organizacion_id)

    def obtener_por_nombre(
        self, db: Session, nombre: str
    ) -> Optional[Organizacion]:
        return db.query(Organizacion).filter(Organizacion.nombre == nombre).first()

    def listar(self, db: Session, organizacion_id: int | None = None) -> list[Organizacion]:
        consulta = db.query(Organizacion)
        if organizacion_id is not None:
            consulta = consulta.filter(Organizacion.id == organizacion_id)
        return consulta.order_by(Organizacion.id.asc()).all()

    def crear(self, db: Session, organizacion: Organizacion) -> Organizacion:
        db.add(organizacion)
        db.commit()
        db.refresh(organizacion)
        return organizacion

    def actualizar(
        self, db: Session, organizacion: Organizacion
    ) -> Organizacion:
        db.commit()
        db.refresh(organizacion)
        return organizacion


class RolRepository:
    def obtener_por_id(self, db: Session, rol_id: int) -> Optional[Rol]:
        return db.get(Rol, rol_id)

    def obtener_por_nombre(self, db: Session, nombre: str) -> Optional[Rol]:
        return db.query(Rol).filter(Rol.nombre == nombre).first()

    def listar(self, db: Session) -> list[Rol]:
        return db.query(Rol).order_by(Rol.id.asc()).all()

    def agregar(self, db: Session, rol: Rol) -> Rol:
        db.add(rol)
        db.commit()
        db.refresh(rol)
        return rol


class UsuarioRepository:
    def obtener_por_email(self, db: Session, email: str) -> Optional[Usuario]:
        return (
            db.query(Usuario)
            .options(joinedload(Usuario.rol))
            .filter(Usuario.email == email)
            .first()
        )

    def obtener_por_id(self, db: Session, usuario_id: int) -> Optional[Usuario]:
        return (
            db.query(Usuario)
            .options(joinedload(Usuario.rol))
            .filter(Usuario.id == usuario_id)
            .first()
        )

    def crear(self, db: Session, usuario: Usuario) -> Usuario:
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario

    def listar_por_rol_nombre(
        self,
        db: Session,
        nombre_rol: str,
        solo_activos: bool = True,
        organizacion_id: Optional[int] = None,
    ) -> list[Usuario]:
        """Lista usuarios que pertenecen a un rol determinado.

        Si se indica `organizacion_id`, acota el resultado a los usuarios de
        esa organizacion.
        """

        query = (
            db.query(Usuario)
            .options(joinedload(Usuario.rol))
            .join(Rol, Rol.id == Usuario.rol_id)
            .filter(Rol.nombre == nombre_rol)
        )
        if solo_activos:
            query = query.filter(Usuario.activo.is_(True))
        if organizacion_id is not None:
            query = query.filter(Usuario.organizacion_id == organizacion_id)
        return query.order_by(Usuario.id.asc()).all()
