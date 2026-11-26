import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..dto import RecursoInventarioRespuesta
from ..integrations import cloud_client
from ..models import OrganizacionCloud, RecursoInventario, RecursoInventarioCloud
from ..repositories import RecursoInventarioRepository
from ..schemas import RecursoInventarioActualizar, RecursoInventarioCrear
from .recursos_cloud_service import RecursosCloudService
from .usuarios_service import OrganizacionService

logger = logging.getLogger(__name__)

SIN_SINCRONIZAR = "No se pudo sincronizar con el Sistema Nacional"
YA_EXISTE_EN_NACIONAL = (
    "El recurso ya existe en el inventario nacional. "
    "Actualizá el inventario y editalo desde el botón Editar."
)
_ERRORES_TRANSPORTE = (
    cloud_client.AutenticacionAplicacionError,
    httpx.RequestError,
    httpx.InvalidURL,
)


@dataclass(frozen=True)
class DisponibilidadRecurso:
    """Fila de disponibilidad nacional de un recurso de la ONG."""

    total: int
    comprometido: int
    disponible: int
    nombre: str | None = None
    unidad: str | None = None


class InventarioService:
    """ABM del inventario local, replicado en el inventario nacional (Cloud).

    Orden de escritura: primero Cloud y después la base local; si la base
    local falla se compensa en Cloud para no dejar stock nacional huérfano.
    """

    def __init__(self) -> None:
        self._repository = RecursoInventarioRepository()
        self._organizaciones = OrganizacionService()
        self._catalogo = RecursosCloudService()

    def listar_recursos(
        self, db: Session, organizacion_id: int
    ) -> list[RecursoInventarioRespuesta]:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        ong_id = self._ong_id(db, organizacion_id)
        # Una sola consulta por listado; si Cloud no responde, el listado
        # local se devuelve igual marcado como no sincronizado.
        disponibilidad = None
        if ong_id is not None:
            try:
                disponibilidad = self._filas_disponibilidad(ong_id)
            except HTTPException:
                logger.warning(
                    "Inventario: Cloud no disponible al listar la ONG %s", ong_id
                )
        if disponibilidad is not None:
            self._sincronizar(db, organizacion_id, disponibilidad)
        recursos = self._repository.listar_de_organizacion(db, organizacion_id)
        return [self._respuesta(r, disponibilidad) for r in recursos]

    def crear_recurso(
        self,
        db: Session,
        organizacion_id: int,
        data: RecursoInventarioCrear,
    ) -> RecursoInventarioRespuesta:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        ong_id = self._ong_vinculada(db, organizacion_id)
        self._validar_no_duplicado(db, organizacion_id, data.tipo_recurso_id)

        # Dar de alta un recurso que ya está en el inventario nacional no se
        # permite: el usuario debe editarlo desde el botón "Editar".
        if data.tipo_recurso_id in self._filas_disponibilidad(ong_id):
            raise HTTPException(409, YA_EXISTE_EN_NACIONAL)

        nombre = self._nombre_en_catalogo(data.tipo_recurso_id)
        if not self._publicar_en_cloud(
            ong_id, data.tipo_recurso_id, data.cantidad_total
        ):
            # Carrera: otra instancia lo publicó entre el GET y el POST.
            raise HTTPException(409, YA_EXISTE_EN_NACIONAL)

        recurso = RecursoInventario(
            organizacion_id=organizacion_id,
            tipo=nombre,
            cantidad_total=data.cantidad_total,
            unidad=data.unidad,
            descripcion=data.descripcion,
        )
        recurso.referencia_cloud = RecursoInventarioCloud(
            tipo_recurso_id=data.tipo_recurso_id
        )
        try:
            creado = self._repository.crear(db, recurso)
        except Exception:
            db.rollback()
            self._compensar(
                cloud_client.eliminar_item_ong,
                ong_id, data.tipo_recurso_id,
            )
            raise
        return self._respuesta_posterior(creado, ong_id)

    def actualizar_recurso(
        self,
        db: Session,
        organizacion_id: int,
        recurso_id: int,
        data: RecursoInventarioActualizar,
    ) -> RecursoInventarioRespuesta:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recurso = self._obtener_recurso_entidad(
            db, recurso_id, organizacion_id
        )
        referencia = recurso.referencia_cloud

        if referencia is None and data.tipo_recurso_id is not None:
            return self._vincular_recurso(db, recurso, data)

        if referencia is None:
            # Fila previa sin equivalencia nacional: sólo se actualiza local.
            self._aplicar_valores(recurso, data)
            actualizado = self._repository.actualizar(db, recurso)
            return self._respuesta(actualizado, None)

        if (data.tipo_recurso_id is not None
                and data.tipo_recurso_id != referencia.tipo_recurso_id):
            raise HTTPException(
                409, "El recurso ya está vinculado a otro recurso nacional"
            )
        ong_id = self._ong_vinculada(db, organizacion_id)
        cantidad_anterior = recurso.cantidad_total
        if data.cantidad_total != cantidad_anterior:
            comprometido = self._comprometido(ong_id, referencia.tipo_recurso_id)
            if data.cantidad_total < comprometido:
                raise HTTPException(
                    409,
                    "La cantidad no puede ser menor a la comprometida en el "
                    f"Sistema Nacional ({comprometido})",
                )
            self._actualizar_en_cloud(
                ong_id, referencia.tipo_recurso_id, data.cantidad_total
            )
        self._aplicar_valores(recurso, data)
        try:
            actualizado = self._repository.actualizar(db, recurso)
        except Exception:
            db.rollback()
            if data.cantidad_total != cantidad_anterior:
                self._compensar(
                    cloud_client.actualizar_item_ong,
                    ong_id, referencia.tipo_recurso_id, cantidad_anterior,
                )
            raise
        return self._respuesta_posterior(actualizado, ong_id)

    def eliminar_recurso(
        self, db: Session, organizacion_id: int, recurso_id: int
    ) -> None:
        self._organizaciones.obtener_organizacion_entidad(db, organizacion_id)
        recurso = self._obtener_recurso_entidad(
            db, recurso_id, organizacion_id
        )
        referencia = recurso.referencia_cloud
        if referencia is not None:
            ong_id = self._ong_vinculada(db, organizacion_id)
            comprometido = self._comprometido(ong_id, referencia.tipo_recurso_id)
            if comprometido > 0:
                raise HTTPException(
                    409,
                    "No se puede eliminar: el recurso tiene "
                    f"{comprometido} unidades comprometidas en el Sistema Nacional",
                )
            respuesta = self._llamar(
                cloud_client.eliminar_item_ong, ong_id, referencia.tipo_recurso_id
            )
            # 404: ya no estaba en Cloud, el objetivo de la baja está cumplido.
            if respuesta.status_code not in (204, 404):
                self._error_cloud(respuesta)
        self._repository.eliminar(db, recurso)

    def _vincular_recurso(
        self,
        db: Session,
        recurso: RecursoInventario,
        data: RecursoInventarioActualizar,
    ) -> RecursoInventarioRespuesta:
        """Vincula una fila previa al catálogo nacional sin pisar el stock."""
        ong_id = self._ong_vinculada(db, recurso.organizacion_id)
        self._validar_no_duplicado(
            db, recurso.organizacion_id, data.tipo_recurso_id, excluir_id=recurso.id
        )
        disponibilidad = self._filas_disponibilidad(ong_id)
        fila = disponibilidad.get(data.tipo_recurso_id)
        creado_en_cloud = False
        if fila is not None:
            # Ya existe en Cloud: se adopta su total, sin POST ni PATCH.
            nombre = fila.nombre or self._catalogo_por_id().get(
                data.tipo_recurso_id
            )
            cantidad = fila.total
        else:
            nombre = self._nombre_en_catalogo(data.tipo_recurso_id)
            creado_en_cloud = self._publicar_en_cloud(
                ong_id, data.tipo_recurso_id, data.cantidad_total
            )
            if creado_en_cloud:
                cantidad = data.cantidad_total
            else:
                # Carrera: el ítem apareció entre el GET y el POST.
                fila = self._filas_disponibilidad(ong_id).get(
                    data.tipo_recurso_id
                )
                if fila is None:
                    raise HTTPException(503, SIN_SINCRONIZAR)
                nombre = fila.nombre or nombre
                cantidad = fila.total

        self._aplicar_valores(recurso, data)
        recurso.cantidad_total = cantidad
        recurso.tipo = nombre or f"Recurso {data.tipo_recurso_id}"
        recurso.referencia_cloud = RecursoInventarioCloud(
            tipo_recurso_id=data.tipo_recurso_id
        )
        try:
            actualizado = self._repository.actualizar(db, recurso)
        except Exception:
            db.rollback()
            if creado_en_cloud:
                self._compensar(
                    cloud_client.eliminar_item_ong,
                    ong_id, data.tipo_recurso_id,
                )
            raise
        return self._respuesta_posterior(actualizado, ong_id)

    def _sincronizar(
        self,
        db: Session,
        organizacion_id: int,
        disponibilidad: dict[int, DisponibilidadRecurso],
    ) -> None:
        """Replica en la base local el estado del inventario nacional.

        Los errores se registran y se revierten: el listado nunca se rompe por
        una falla al sincronizar.
        """
        try:
            vinculados = {
                recurso.referencia_cloud.tipo_recurso_id: recurso
                for recurso in self._repository.listar_de_organizacion(
                    db, organizacion_id
                )
                if recurso.referencia_cloud is not None
            }
            catalogo: dict[int, str] | None = None
            cambios = False
            for tipo_recurso_id, fila in disponibilidad.items():
                recurso = vinculados.get(tipo_recurso_id)
                if recurso is not None:
                    if recurso.cantidad_total != fila.total:
                        recurso.cantidad_total = fila.total
                        cambios = True
                    continue
                if fila.total <= 0:
                    logger.warning(
                        "Inventario: se omite el recurso nacional %s de la ONG "
                        "%s porque su total no es positivo",
                        tipo_recurso_id, organizacion_id,
                    )
                    continue
                if fila.nombre:
                    nombre = fila.nombre
                else:
                    if catalogo is None:
                        catalogo = self._catalogo_por_id()
                    nombre = catalogo.get(tipo_recurso_id)
                recurso = RecursoInventario(
                    organizacion_id=organizacion_id,
                    tipo=nombre or f"Recurso {tipo_recurso_id}",
                    cantidad_total=fila.total,
                    unidad=fila.unidad,
                    descripcion=None,
                )
                recurso.referencia_cloud = RecursoInventarioCloud(
                    tipo_recurso_id=tipo_recurso_id
                )
                db.add(recurso)
                cambios = True
            if cambios:
                db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Inventario: no se pudo sincronizar la ONG %s con Cloud",
                organizacion_id,
            )

    def _catalogo_por_id(self) -> dict[int, str]:
        try:
            return {
                recurso.id: recurso.nombre for recurso in self._catalogo.listar()
            }
        except HTTPException:
            logger.warning(
                "Inventario: catálogo nacional no disponible al importar"
            )
            return {}

    @staticmethod
    def _aplicar_valores(
        recurso: RecursoInventario, data: RecursoInventarioActualizar
    ) -> None:
        recurso.cantidad_total = data.cantidad_total
        recurso.unidad = data.unidad
        recurso.descripcion = data.descripcion

    @staticmethod
    def _ong_id(db: Session, organizacion_id: int) -> int | None:
        vinculo = db.get(OrganizacionCloud, organizacion_id)
        return vinculo.ong_id if vinculo is not None else None

    def _ong_vinculada(self, db: Session, organizacion_id: int) -> int:
        ong_id = self._ong_id(db, organizacion_id)
        if ong_id is None:
            raise HTTPException(409, "La ONG no está vinculada al Sistema Nacional")
        return ong_id

    @staticmethod
    def _validar_no_duplicado(
        db: Session,
        organizacion_id: int,
        tipo_recurso_id: int,
        excluir_id: int | None = None,
    ) -> None:
        consulta = (
            db.query(RecursoInventarioCloud.recurso_id)
            .join(
                RecursoInventario,
                RecursoInventario.id == RecursoInventarioCloud.recurso_id,
            )
            .filter(
                RecursoInventario.organizacion_id == organizacion_id,
                RecursoInventarioCloud.tipo_recurso_id == tipo_recurso_id,
            )
        )
        if excluir_id is not None:
            consulta = consulta.filter(RecursoInventario.id != excluir_id)
        if consulta.first() is not None:
            raise HTTPException(
                409, "La ONG ya tiene ese recurso nacional en su inventario"
            )

    def _nombre_en_catalogo(self, tipo_recurso_id: int) -> str:
        try:
            catalogo = self._catalogo.listar()
        except HTTPException as exc:
            if exc.status_code in (502, 503):
                raise HTTPException(503, SIN_SINCRONIZAR) from None
            raise
        recurso = next((r for r in catalogo if r.id == tipo_recurso_id), None)
        if recurso is None:
            raise HTTPException(404, "Recurso nacional no encontrado")
        return recurso.nombre

    @staticmethod
    def _llamar(funcion, *argumentos) -> httpx.Response:
        """Ejecuta una operación en Cloud; caída, 5xx o auth se informan como 503."""
        try:
            token = cloud_client.obtener_token_aplicacion()
            respuesta = funcion(*argumentos, token)
        except _ERRORES_TRANSPORTE:
            raise HTTPException(503, SIN_SINCRONIZAR) from None
        if respuesta.status_code >= 500 or respuesta.status_code in (401, 403):
            raise HTTPException(503, SIN_SINCRONIZAR)
        return respuesta

    @staticmethod
    def _error_cloud(respuesta: httpx.Response) -> None:
        raise HTTPException(
            502,
            f"Sistema Nacional respondió con estado {respuesta.status_code}: "
            f"{RecursosCloudService._detalle(respuesta)}",
        )

    def _publicar_en_cloud(
        self, ong_id: int, tipo_recurso_id: int, cantidad: int
    ) -> bool:
        """Publica el ítem en Cloud; devuelve False si ya existía (409)."""
        respuesta = self._llamar(
            cloud_client.asignar_item_ong, ong_id, tipo_recurso_id, cantidad
        )
        if respuesta.status_code == 201:
            return True
        if respuesta.status_code == 409:
            return False
        self._error_cloud(respuesta)

    def _actualizar_en_cloud(
        self, ong_id: int, tipo_recurso_id: int, cantidad: int
    ) -> None:
        respuesta = self._llamar(
            cloud_client.actualizar_item_ong, ong_id, tipo_recurso_id, cantidad
        )
        if respuesta.status_code == 200:
            return
        if respuesta.status_code == 404:
            # El ítem no figura en Cloud: se vuelve a publicar. Si otra
            # instancia lo creó en el medio, se reintenta la actualización.
            if self._publicar_en_cloud(ong_id, tipo_recurso_id, cantidad):
                return
            respuesta = self._llamar(
                cloud_client.actualizar_item_ong,
                ong_id, tipo_recurso_id, cantidad,
            )
            if respuesta.status_code == 200:
                return
        self._error_cloud(respuesta)

    @staticmethod
    def _compensar(funcion, *argumentos) -> None:
        """Deshace en Cloud sin ocultar el error local original."""
        try:
            token = cloud_client.obtener_token_aplicacion()
            funcion(*argumentos, token)
        except Exception:
            logger.exception(
                "Inventario: no se pudo compensar en Cloud %s%s",
                funcion.__name__, argumentos,
            )

    def _filas_disponibilidad(
        self, ong_id: int
    ) -> dict[int, DisponibilidadRecurso]:
        """Devuelve la disponibilidad nacional indexada por tipo de recurso."""
        respuesta = self._llamar(cloud_client.disponibilidad_ong, ong_id)
        if respuesta.status_code != 200:
            self._error_cloud(respuesta)
        try:
            datos = respuesta.json()
            # Versiones viejas devolvían directamente la lista.
            filas = datos.get("disponibles") if isinstance(datos, dict) else datos
            return {
                int(fila["tipo_recurso_id"]): DisponibilidadRecurso(
                    total=int(fila.get("total", 0)),
                    comprometido=int(fila["comprometido"]),
                    disponible=int(fila["disponible"]),
                    nombre=fila.get("nombre") or None,
                    unidad=fila.get("unidad") or None,
                )
                for fila in (filas or [])
            }
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(
                502, "El Sistema Nacional devolvió una disponibilidad inválida"
            ) from None

    def _comprometido(self, ong_id: int, tipo_recurso_id: int) -> int:
        fila = self._filas_disponibilidad(ong_id).get(tipo_recurso_id)
        return fila.comprometido if fila is not None else 0

    def _respuesta_posterior(
        self, recurso: RecursoInventario, ong_id: int
    ) -> RecursoInventarioRespuesta:
        """Respuesta tras escribir: la consulta a Cloud es de mejor esfuerzo."""
        try:
            disponibilidad = self._filas_disponibilidad(ong_id)
        except HTTPException:
            disponibilidad = None
        return self._respuesta(recurso, disponibilidad)

    @staticmethod
    def _respuesta(
        recurso: RecursoInventario,
        disponibilidad: dict[int, DisponibilidadRecurso] | None,
    ) -> RecursoInventarioRespuesta:
        referencia = recurso.referencia_cloud
        tipo_recurso_id = referencia.tipo_recurso_id if referencia else None
        valores = None
        if disponibilidad is not None and tipo_recurso_id is not None:
            valores = disponibilidad.get(tipo_recurso_id)
        return RecursoInventarioRespuesta(
            id=recurso.id,
            organizacion_id=recurso.organizacion_id,
            tipo=recurso.tipo,
            cantidad_total=recurso.cantidad_total,
            unidad=recurso.unidad,
            descripcion=recurso.descripcion,
            tipo_recurso_id=tipo_recurso_id,
            comprometido=valores.comprometido if valores else None,
            disponible=valores.disponible if valores else None,
            sincronizado=valores is not None,
        )

    def _obtener_recurso_entidad(
        self, db: Session, recurso_id: int, organizacion_id: int
    ) -> RecursoInventario:
        """Resuelve el recurso validando que pertenezca a la organizacion.

        El chequeo de pertenencia evita editar o borrar el recurso de otra
        ONG entrando por la ruta equivocada: si el id existe pero cuelga de
        otra organizacion, para esta ruta el recurso no existe.
        """
        recurso = self._repository.obtener_por_id(db, recurso_id)
        if recurso is None or recurso.organizacion_id != organizacion_id:
            raise HTTPException(
                status_code=404, detail="Recurso no encontrado"
            )
        return recurso
