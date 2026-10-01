from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..dto import (
    AuthRespuesta,
    OrganizacionRespuesta,
    RolRespuesta,
    UsuarioRespuesta,
)
from ..models import Organizacion, Rol, Usuario
from ..repositories import (
    OrganizacionRepository,
    RolRepository,
    UsuarioRepository,
)
from ..schemas import (
    LoginSolicitud,
    OrganizacionActualizar,
    OrganizacionCrear,
    UsuarioCrear,
)
from .security_service import generar_token, hashear_password, verificar_password

ROLES_INICIALES = [
    "OPERADOR_MUNICIPAL",
    "CENTRO_COORDINADOR",
    "REPRESENTANTE_ONG",
    "DIRECTOR_AUDITOR",
]

ORGANIZACION_ONU = {
    "nombre": "Organización de las Naciones Unidas",
    "tipo": "ong",
    "email": "ong@un.org",
    "telefono": "754 1200",
    "activa": True,
}

# La contraseña de cada usuario inicial es su propio email.
USUARIOS_INICIALES = [
    {
        "email": "municipio@municipio.com",
        "nombre": "Laura",
        "apellido": "Gómez",
        "rol": "OPERADOR_MUNICIPAL",
        "organizacion": None,
    },
    {
        "email": "coordinador@coordinador.com",
        "nombre": "Carlos",
        "apellido": "Fernández",
        "rol": "CENTRO_COORDINADOR",
        "organizacion": None,
    },
    {
        "email": "ong@ong.com",
        "nombre": "María",
        "apellido": "Rodríguez",
        "rol": "REPRESENTANTE_ONG",
        "organizacion": ORGANIZACION_ONU,
    },
    {
        "email": "auditor@auditor.com",
        "nombre": "Jorge",
        "apellido": "Martínez",
        "rol": "DIRECTOR_AUDITOR",
        "organizacion": None,
    },
]


class OrganizacionService:
    def __init__(self) -> None:
        self._repository = OrganizacionRepository()

    def listar_organizaciones(
        self, db: Session, organizacion_id: int | None = None
    ) -> list[OrganizacionRespuesta]:
        organizaciones = self._repository.listar(db, organizacion_id)
        return [OrganizacionRespuesta.model_validate(o) for o in organizaciones]

    def obtener_organizacion(
        self, db: Session, organizacion_id: int
    ) -> OrganizacionRespuesta:
        organizacion = self._obtener_organizacion_entidad(
            db, organizacion_id
        )
        return OrganizacionRespuesta.model_validate(organizacion)

    def obtener_organizacion_entidad(
        self, db: Session, organizacion_id: int
    ) -> Organizacion:
        """Devuelve la entidad para uso de otros services."""
        return self._obtener_organizacion_entidad(db, organizacion_id)

    def crear_organizacion(
        self, db: Session, data: OrganizacionCrear
    ) -> OrganizacionRespuesta:
        creada = self._repository.crear(db, Organizacion(**data.model_dump()))
        return OrganizacionRespuesta.model_validate(creada)

    def actualizar_organizacion(
        self, db: Session, organizacion_id: int, data: OrganizacionActualizar
    ) -> OrganizacionRespuesta:
        organizacion = self._obtener_organizacion_entidad(
            db, organizacion_id
        )
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(organizacion, field, value)
        actualizada = self._repository.actualizar(db, organizacion)
        return OrganizacionRespuesta.model_validate(actualizada)

    def _obtener_organizacion_entidad(
        self, db: Session, organizacion_id: int
    ) -> Organizacion:
        organizacion = self._repository.obtener_por_id(db, organizacion_id)
        if organizacion is None:
            raise HTTPException(
                status_code=404, detail="Organización no encontrada"
            )
        return organizacion


class RolService:
    def __init__(self) -> None:
        self._repository = RolRepository()

    def listar_roles(self, db: Session) -> list[RolRespuesta]:
        roles = self._repository.listar(db)
        return [RolRespuesta.model_validate(r) for r in roles]

    def sembrar_roles(self, db: Session) -> None:
        """Inserta los roles base solo si no existen (idempotente)."""
        for nombre in ROLES_INICIALES:
            if self._repository.obtener_por_nombre(db, nombre) is None:
                try:
                    self._repository.agregar(db, Rol(nombre=nombre))
                except IntegrityError:
                    db.rollback()
                    # Otro proceso puede haber sembrado el mismo rol al arrancar.
                    if self._repository.obtener_por_nombre(db, nombre) is None:
                        raise


class AuthService:
    def __init__(self) -> None:
        self._usuarios = UsuarioRepository()
        self._roles = RolRepository()
        self._organizaciones = OrganizacionRepository()

    def sembrar_usuarios_iniciales(self, db: Session) -> None:
        """Inserta los usuarios base de prueba solo si no existen (idempotente)."""
        for datos in USUARIOS_INICIALES:
            if self._usuarios.obtener_por_email(db, datos["email"]) is not None:
                continue

            rol = self._roles.obtener_por_nombre(db, datos["rol"])
            if rol is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"El rol {datos['rol']} debe existir antes de sembrar usuarios",
                )

            organizacion_id = None
            if datos["organizacion"] is not None:
                organizacion_id = self._sembrar_organizacion(
                    db, datos["organizacion"]
                ).id

            usuario = Usuario(
                email=datos["email"],
                password_hash=hashear_password(datos["email"]),
                nombre=datos["nombre"],
                apellido=datos["apellido"],
                rol_id=rol.id,
                organizacion_id=organizacion_id,
                activo=True,
            )
            try:
                self._usuarios.crear(db, usuario)
            except IntegrityError:
                db.rollback()
                # Otro proceso puede haber sembrado el mismo usuario al arrancar.
                if self._usuarios.obtener_por_email(db, datos["email"]) is None:
                    raise

    def _sembrar_organizacion(
        self, db: Session, campos: dict[str, str | bool]
    ) -> Organizacion:
        """Inserta la organización inicial solo si no existe (idempotente)."""
        organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
        if organizacion is not None:
            return organizacion
        try:
            return self._organizaciones.crear(db, Organizacion(**campos))
        except IntegrityError:
            db.rollback()
            # Otro proceso puede haber sembrado la misma organización al arrancar.
            organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
            if organizacion is None:
                raise
            return organizacion

    def registrar_usuario(self, db: Session, data: UsuarioCrear) -> Usuario:
        if self._usuarios.obtener_por_email(db, data.email) is not None:
            raise HTTPException(
                status_code=409, detail="El email ya está registrado"
            )

        rol = self._roles.obtener_por_id(db, data.rol_id)
        if rol is None:
            raise HTTPException(status_code=404, detail="Rol no encontrado")

        if rol.nombre == "REPRESENTANTE_ONG" and data.organizacion_id is None:
            raise HTTPException(400, "El representante de ONG debe pertenecer a una organización")
        if data.organizacion_id is not None:
            OrganizacionService().obtener_organizacion(db, data.organizacion_id)

        usuario = Usuario(
            email=data.email,
            password_hash=hashear_password(data.password),
            nombre=data.nombre,
            apellido=data.apellido,
            rol_id=rol.id,
            organizacion_id=data.organizacion_id,
            activo=True,
        )
        try:
            return self._usuarios.crear(db, usuario)
        except IntegrityError as exc:
            db.rollback()
            if self._usuarios.obtener_por_email(db, data.email) is not None:
                raise HTTPException(
                    status_code=409, detail="El email ya está registrado"
                ) from exc
            raise

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
