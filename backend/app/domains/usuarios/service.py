from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Organizacion, Rol, Usuario
from .repository import (
    OrganizacionRepository,
    RolRepository,
    UsuarioRepository,
)
from .schemas import (
    AuthRespuesta,
    LoginSolicitud,
    OrganizacionActualizar,
    OrganizacionCrear,
    UsuarioCrear,
    UsuarioRespuesta,
)
from .security import generar_token, hashear_password, verificar_password

ROLES_INICIALES = [
    "OPERADOR_MUNICIPAL",
    "CENTRO_COORDINADOR",
    "REPRESENTANTE_ONG",
    "DIRECTOR_AUDITOR",
]


class OrganizacionService:
    def __init__(self) -> None:
        self._repository = OrganizacionRepository()

    def listar_organizaciones(self, db: Session) -> list[Organizacion]:
        return self._repository.listar(db)

    def obtener_organizacion(
        self, db: Session, organizacion_id: int
    ) -> Organizacion:
        organizacion = self._repository.obtener_por_id(db, organizacion_id)
        if organizacion is None:
            raise HTTPException(
                status_code=404, detail="Organización no encontrada"
            )
        return organizacion

    def crear_organizacion(
        self, db: Session, data: OrganizacionCrear
    ) -> Organizacion:
        return self._repository.crear(db, Organizacion(**data.model_dump()))

    def actualizar_organizacion(
        self, db: Session, organizacion_id: int, data: OrganizacionActualizar
    ) -> Organizacion:
        organizacion = self.obtener_organizacion(db, organizacion_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(organizacion, field, value)
        return self._repository.actualizar(db, organizacion)


class RolService:
    def __init__(self) -> None:
        self._repository = RolRepository()

    def listar_roles(self, db: Session) -> list[Rol]:
        return self._repository.listar(db)

    def sembrar_roles(self, db: Session) -> None:
        """Inserta los roles base solo si no existen (idempotente)."""
        for nombre in ROLES_INICIALES:
            if self._repository.obtener_por_nombre(db, nombre) is None:
                self._repository.agregar(db, Rol(nombre=nombre))


class AuthService:
    def __init__(self) -> None:
        self._usuarios = UsuarioRepository()
        self._roles = RolRepository()

    def registrar_usuario(self, db: Session, data: UsuarioCrear) -> Usuario:
        if self._usuarios.obtener_por_email(db, data.email) is not None:
            raise HTTPException(
                status_code=409, detail="El email ya está registrado"
            )

        rol = self._roles.obtener_por_id(db, data.rol_id)
        if rol is None:
            raise HTTPException(status_code=404, detail="Rol no encontrado")

        usuario = Usuario(
            email=data.email,
            password_hash=hashear_password(data.password),
            nombre=data.nombre,
            apellido=data.apellido,
            rol_id=rol.id,
            municipio_id=data.municipio_id,
            organizacion_id=data.organizacion_id,
            activo=True,
        )
        return self._usuarios.crear(db, usuario)

    def login(self, db: Session, data: LoginSolicitud) -> AuthRespuesta:
        usuario = self._usuarios.obtener_por_email(db, data.email)

        if usuario is None or not verificar_password(
            data.password, usuario.password_hash
        ):
            raise HTTPException(
                status_code=401, detail="Credenciales inválidas"
            )

        if not usuario.activo:
            raise HTTPException(
                status_code=403, detail="El usuario está inactivo"
            )

        return self.construir_auth_response(usuario)

    def construir_auth_response(self, usuario: Usuario) -> AuthRespuesta:
        return AuthRespuesta(
            access_token=generar_token(usuario.id, usuario.rol_id, usuario.rol.nombre),
            token_type="bearer",
            rol=usuario.rol.nombre,
            usuario=UsuarioRespuesta.model_validate(usuario),
        )
