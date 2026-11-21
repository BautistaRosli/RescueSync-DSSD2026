import logging
import os
import re

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..dto import (
    AuthRespuesta,
    OrganizacionRespuesta,
    RolRespuesta,
    UsuarioRespuesta,
)
from ..models import Organizacion, OrganizacionCloud, Rol, Usuario
from ..integrations import cloud_client
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

logger = logging.getLogger(__name__)
LIMITE_DETALLE_CLOUD = 300
ONGS_DEMO_CLOUD_POR_CUIT = {
    "30-12345678-5": 8,
    "30-87654321-4": 9,
}

ROLES_INICIALES = [
    "OPERADOR_MUNICIPAL",
    "CENTRO_COORDINADOR",
    "REPRESENTANTE_ONG",
    "DIRECTOR_AUDITOR",
]

ORGANIZACION_ONU = {
    "nombre": "Organización de las Naciones Unidas",
    "tipo": "ong",
    "cuit": "30-12345678-5",
    "email": "ong@onu.org",
    "telefono": "754 1200",
    "activa": True,
}

ORGANIZACION_UNICEF = {
    "nombre": "UNICEF",
    "tipo": "ong",
    "cuit": "30-87654321-4",
    "email": "unicef@unicef.org",
    "telefono": "754 1201",
    "activa": True,
}

CONFIGURACION_ONG_INICIALES = {
    ORGANIZACION_ONU["nombre"]: ("ONU", 2),
    ORGANIZACION_UNICEF["nombre"]: ("UNICEF", 3),
}

# Sólo en development: cada cuenta de demostración usa su email como contraseña.
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
        "email": "unicef@unicef.org",
        "nombre": "Ana",
        "apellido": "Pérez",
        "rol": "REPRESENTANTE_ONG",
        "organizacion": ORGANIZACION_UNICEF,
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
        ong_id = self._registrar_ong_cloud(data) if data.tipo == "ong" else None
        try:
            organizacion = Organizacion(**data.model_dump(exclude={"cuit"}))
            if ong_id is not None:
                organizacion.referencia_cloud = OrganizacionCloud(ong_id=ong_id)
            creada = self._repository.crear(db, organizacion)
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(503, "No se pudo completar el registro de la organización") from None
        return OrganizacionRespuesta.model_validate(creada)

    def _registrar_ong_cloud(
        self, data: OrganizacionCrear, recuperar_duplicada: bool = False
    ) -> int:
        try:
            token = cloud_client.obtener_token_aplicacion()
            respuesta = cloud_client.registrar_ong(data.cuit, data.nombre, data.email, token)
        except (cloud_client.AutenticacionAplicacionError, httpx.RequestError, httpx.InvalidURL, ValueError) as exc:
            logger.warning("No se pudo registrar la ONG en Cloud: %s", type(exc).__name__)
            raise HTTPException(503, "Registro de ONG en Cloud no disponible") from None
        if respuesta.status_code == 409:
            logger.info("Cloud rechazó el registro de ONG por CUIT duplicado (status=%s)", respuesta.status_code)
            if recuperar_duplicada:
                return self._recuperar_ong_cloud_duplicada(data, respuesta, token)
            raise HTTPException(409, "El CUIT ya está registrado en Cloud")

        if respuesta.status_code != 201:
            detalle = self._detalle_respuesta_cloud(respuesta)
            logger.warning(
                "Cloud rechazó el registro de ONG (status=%s, detalle=%s)",
                respuesta.status_code,
                detalle,
            )
            raise HTTPException(
                502,
                f"Cloud respondió con estado {respuesta.status_code}: {detalle}",
            ) from None

        try:
            datos = respuesta.json()
        except (ValueError, TypeError):
            datos = None
        identidad = {"cuit": data.cuit, "razon_social": data.nombre.strip(), "email": data.email}
        if (not isinstance(datos, dict) or type(datos.get("id")) is not int
                or datos["id"] <= 0
                or any(datos.get(campo) != valor for campo, valor in identidad.items())):
            detalle = self._detalle_respuesta_cloud(respuesta)
            logger.warning(
                "Cloud devolvió una respuesta inválida al registrar una ONG (status=%s, cuerpo=%s)",
                respuesta.status_code,
                detalle,
            )
            raise HTTPException(
                502,
                f"Cloud devolvió una respuesta inválida para el registro de ONG: {detalle}",
            ) from None
        return datos["id"]

    def _recuperar_ong_cloud_duplicada(
        self, data: OrganizacionCrear, respuesta: httpx.Response, token: str
    ) -> int:
        """Recupera una ONG demo existente y valida su identidad contra Cloud."""
        ong_id = self._extraer_id_ong_cloud(respuesta)
        if ong_id is None:
            ong_id = ONGS_DEMO_CLOUD_POR_CUIT.get(data.cuit)
        if ong_id is None:
            raise RuntimeError(
                f"Cloud informó que la ONG '{data.nombre}' ya existe, pero no devolvió su id "
                "y no hay un id demo de desarrollo configurado para su CUIT"
            )

        try:
            verificacion = cloud_client.obtener_ong(ong_id, token)
        except (httpx.RequestError, httpx.InvalidURL) as exc:
            raise RuntimeError(
                f"No se pudo verificar en Cloud la ONG demo '{data.nombre}' (id={ong_id}): "
                f"{type(exc).__name__}"
            ) from exc
        if verificacion.status_code != 200:
            detalle = self._detalle_respuesta_cloud(verificacion)
            raise RuntimeError(
                f"No se pudo verificar en Cloud la ONG demo '{data.nombre}' (id={ong_id}): "
                f"Cloud respondió con estado {verificacion.status_code}: {detalle}"
            )

        try:
            datos = verificacion.json()
        except (ValueError, TypeError):
            datos = None
        if not isinstance(datos, dict) or type(datos.get("id")) is not int or datos["id"] != ong_id:
            raise RuntimeError(
                f"Cloud devolvió una respuesta inválida al verificar la ONG demo "
                f"'{data.nombre}' (id={ong_id})"
            )
        equivalencias = {
            "cuit": data.cuit,
            "razon_social": data.nombre.strip(),
            "email": data.email,
        }
        if any(campo in datos and datos[campo] != valor for campo, valor in equivalencias.items()):
            raise RuntimeError(
                f"La ONG demo '{data.nombre}' no coincide con la identidad de Cloud para id={ong_id}"
            )
        return ong_id

    @staticmethod
    def _extraer_id_ong_cloud(respuesta: httpx.Response) -> int | None:
        try:
            cuerpo = respuesta.json()
        except (ValueError, TypeError):
            return None

        def buscar(valor: object) -> int | None:
            if isinstance(valor, dict):
                for clave in ("id", "ong_id"):
                    if type(valor.get(clave)) is int and valor[clave] > 0:
                        return valor[clave]
                for anidado in valor.values():
                    encontrado = buscar(anidado)
                    if encontrado is not None:
                        return encontrado
            elif isinstance(valor, list):
                for anidado in valor:
                    encontrado = buscar(anidado)
                    if encontrado is not None:
                        return encontrado
            return None

        return buscar(cuerpo)

    @staticmethod
    def _detalle_respuesta_cloud(respuesta: httpx.Response) -> str:
        """Obtiene un detalle acotado sin exponer credenciales en errores o logs."""
        try:
            datos = respuesta.json()
        except (ValueError, TypeError):
            datos = None

        detalle = None
        if isinstance(datos, dict):
            for campo in ("detail", "message"):
                if isinstance(datos.get(campo), (str, int, float, bool)):
                    detalle = str(datos[campo])
                    break
        if detalle is None:
            detalle = respuesta.text or "sin detalle"

        detalle = detalle[:LIMITE_DETALLE_CLOUD]
        return re.sub(
            r"(?i)((?:access_token|token|password|contraseña|credential|secret)\s*[=:]\s*)([^,;\s}\]]+)",
            r"\1[redactado]",
            detalle,
        )

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
        if os.getenv("APP_ENV") != "development":
            return
        for datos in USUARIOS_INICIALES:
            usuario_existente = self._usuarios.obtener_por_email(
                db, datos["email"]
            )
            if usuario_existente is not None:
                if datos["organizacion"] is not None:
                    organizacion = self._sembrar_organizacion(
                        db, datos["organizacion"]
                    )
                    if usuario_existente.organizacion_id != organizacion.id:
                        usuario_existente.organizacion_id = organizacion.id
                        db.commit()
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
        """Conserva el registro local y reconcilia su identidad nacional."""
        configuracion = CONFIGURACION_ONG_INICIALES.get(campos["nombre"])
        organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
        if organizacion is None:
            if configuracion is not None:
                self._organizaciones.bloquear_precarga(db, configuracion[1])
            organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
            try:
                if organizacion is None:
                    organizacion = self._organizaciones.crear(db, Organizacion(**campos))
                else:
                    db.commit()  # Libera el bloqueo de creación antes de acceder a Cloud.
            except IntegrityError:
                db.rollback()
                organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
                if organizacion is None:
                    raise
        identificador_local = organizacion.id
        if configuracion is not None:
            self._reconciliar_ong_cloud(db, identificador_local, configuracion[0])
        return self._organizaciones.obtener_por_id(db, identificador_local)

    def _reconciliar_ong_cloud(self, db: Session, organizacion_id: int, clave: str) -> None:
        variable_id = f"CLOUD_{clave}_ONG_ID"
        cuit = os.getenv(f"CLOUD_{clave}_CUIT", "").strip()
        id_configurado = os.getenv(variable_id, "").strip()
        ong_id = None
        try:
            organizacion = self._organizaciones.obtener_por_id(db, organizacion_id)
            coincidencias = self._organizaciones.buscar_precarga(db, organizacion.nombre)
            if len(coincidencias) != 1 or organizacion.tipo != "ong":
                logger.warning("Precarga %s: organización local ambigua o de otro tipo; revise los registros antes de vincular.", clave)
                return
            referencia = db.get(OrganizacionCloud, organizacion_id, populate_existing=True)
            if referencia is not None:
                if id_configurado and id_configurado != str(referencia.ong_id):
                    logger.warning("Precarga %s: %s contradice la vinculación; se conserva la existente.",
                                   clave, variable_id)
                return
            if not cuit:
                logger.warning("Precarga %s: configure CLOUD_%s_CUIT para vincular con Cloud; demo local disponible.",
                               clave, clave)
                return
            organizacion = self._organizaciones.obtener_para_vincular(db, organizacion_id)
            # Otra precarga puede haber completado el vínculo mientras se esperaba la fila.
            if db.get(OrganizacionCloud, organizacion_id, populate_existing=True) is not None:
                db.rollback()
                return
            datos = OrganizacionCrear(nombre=organizacion.nombre, tipo="ong",
                                      email=organizacion.email, cuit=cuit)
            if id_configurado:
                if not id_configurado.isascii() or not id_configurado.isdecimal() or int(id_configurado) <= 0:
                    raise ValueError()
                candidato = int(id_configurado)
                token = cloud_client.obtener_token_aplicacion()
                respuesta = cloud_client.obtener_ong(candidato, token)
                ficha = respuesta.json() if respuesta.status_code == 200 else None
                identidad = {"id": candidato, "cuit": datos.cuit,
                             "razon_social": datos.nombre.strip(), "email": datos.email}
                if (not isinstance(ficha, dict) or type(ficha.get("id")) is not int
                        or any(ficha.get(campo) != valor for campo, valor in identidad.items())):
                    raise ValueError()
                ong_id = candidato
            else:
                ong_id = OrganizacionService()._registrar_ong_cloud(datos)
            # Sin HTTP bajo el bloqueo común; impide asignar el mismo ID a dos ONG.
            self._organizaciones.bloquear_precarga(db, 4)
            if self._organizaciones.referencia_nacional_ocupada(db, ong_id, organizacion_id):
                logger.warning("Precarga %s: ID nacional ocupado por otra organización local; revise %s.",
                               clave, variable_id)
                db.rollback()
                return
            organizacion.referencia_cloud = OrganizacionCloud(ong_id=ong_id)
            self._organizaciones.actualizar(db, organizacion)
            logger.info("Precarga %s: vinculación guardada; %s=%s.", clave, variable_id, ong_id)
        except HTTPException as error:
            db.rollback()
            if error.status_code == 409:
                logger.warning("Precarga %s: CUIT ya registrado; configure %s con el ID confirmado en Cloud.",
                               clave, variable_id)
            else:
                logger.warning("Precarga %s: Cloud no disponible; se reintentará en el próximo arranque.", clave)
        except (cloud_client.AutenticacionAplicacionError, httpx.RequestError,
                httpx.InvalidURL, ValueError, TypeError):
            db.rollback()
            logger.warning("Precarga %s: no se pudo verificar la identidad; revise CLOUD_%s_CUIT, %s y disponibilidad de Cloud.",
                           clave, clave, variable_id)
        except SQLAlchemyError:
            db.rollback()
            logger.warning("Precarga %s: no se pudo guardar la vinculación; configure %s=%s para reintentar por consulta.",
                           clave, variable_id, ong_id if ong_id is not None else "<ID confirmado en Cloud>")
        if organizacion is not None:
            self._vincular_organizacion_cloud(db, organizacion, campos)
            return organizacion

        datos = OrganizacionCrear(**campos)
        ong_id = self._ong_id_demo_cloud(datos)
        try:
            organizacion = self._organizaciones.crear(
                db, Organizacion(**datos.model_dump(exclude={"cuit"}))
            )
            if ong_id is not None:
                organizacion.referencia_cloud = OrganizacionCloud(ong_id=ong_id)
                self._organizaciones.actualizar(db, organizacion)
            return organizacion
        except IntegrityError:
            db.rollback()
            # Otro proceso puede haber sembrado la misma organización al arrancar.
            organizacion = self._organizaciones.obtener_por_nombre(db, campos["nombre"])
            if organizacion is None:
                raise
            self._vincular_organizacion_cloud(db, organizacion, campos)
            return organizacion

    def _vincular_organizacion_cloud(
        self,
        db: Session,
        organizacion: Organizacion,
        campos: dict[str, str | bool],
    ) -> None:
        """Vincula una organización demo existente que aún no tiene referencia Cloud."""
        if organizacion.referencia_cloud is not None:
            return
        datos = OrganizacionCrear(**campos)
        ong_id = self._ong_id_demo_cloud(datos)
        if ong_id is None:
            return
        try:
            organizacion.referencia_cloud = OrganizacionCloud(ong_id=ong_id)
            self._organizaciones.actualizar(db, organizacion)
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(
                503,
                "No se pudo persistir la vinculación de la organización demo con Cloud",
            ) from None

    def _ong_id_demo_cloud(self, datos: OrganizacionCrear) -> int | None:
        """Registra en Cloud solo las organizaciones ONG sembradas en development."""
        if os.getenv("APP_ENV") != "development" or datos.tipo != "ong":
            return None
        try:
            return OrganizacionService()._registrar_ong_cloud(datos, recuperar_duplicada=True)
        except HTTPException as exc:
            raise RuntimeError(
                f"No se pudo vincular la organización demo '{datos.nombre}' con Cloud: "
                f"{exc.detail}"
            ) from exc

    def registrar_usuario(self, db: Session, data: UsuarioCrear) -> AuthRespuesta:
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
            creado = self._usuarios.crear(db, usuario)
        except IntegrityError as exc:
            db.rollback()
            if self._usuarios.obtener_por_email(db, data.email) is not None:
                raise HTTPException(
                    status_code=409, detail="El email ya está registrado"
                ) from exc
            raise
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(503, "No se pudo completar el registro") from None
        return self.construir_auth_response(creado)

    def login(self, db: Session, data: LoginSolicitud) -> AuthRespuesta:
        usuario = self._usuarios.obtener_por_email(db, data.email)

        if usuario is None or not verificar_password(data.password, usuario.password_hash):
            raise HTTPException(
                status_code=401, detail="Credenciales inválidas"
            )

        if not usuario.activo:
            raise HTTPException(
                status_code=403, detail="El usuario está inactivo"
            )

        return self.construir_auth_response(usuario)

    def usuario_actual(self, usuario: Usuario) -> UsuarioRespuesta:
        """Proyecta el usuario autenticado al DTO de salida sin datos sensibles."""
        return UsuarioRespuesta.model_validate(usuario)

    def construir_auth_response(self, usuario: Usuario) -> AuthRespuesta:
        return AuthRespuesta(
            access_token=generar_token(usuario.id, usuario.rol_id, usuario.rol.nombre),
            token_type="bearer",
            rol=usuario.rol.nombre,
            usuario=UsuarioRespuesta.model_validate(usuario),
        )
