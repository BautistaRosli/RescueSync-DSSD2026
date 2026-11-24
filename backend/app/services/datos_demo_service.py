"""Carga idempotente de datos de demostración para desarrollo."""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Emergencia,
    EstadoEmergencia,
    LoteNecesidad,
    NivelGravedad,
    OfertaAyuda,
    OfertaItem,
    AporteOfertaItem,
    Organizacion,
    RecursoInventario,
    LoteRecursoCloud,
)
from ..schemas.recursos_cloud_schema import RecursoCloudCrear
from .recursos_cloud_service import RecursosCloudService
from ..utils.recursos import normalizar_nombre_recurso

PREFIJO_DEMO = "[DEMO DASHBOARD]"
CANTIDAD_EMERGENCIAS_DEMO = 10

logger = logging.getLogger(__name__)

_DESFASES_REGISTRO_DEMO = (
    timedelta(weeks=6, days=1, hours=4),
    timedelta(weeks=6, days=1, hours=12),
    timedelta(weeks=5, days=3, hours=7),
    timedelta(weeks=4, days=6, hours=2),
    timedelta(weeks=4, days=1, hours=10),
    timedelta(weeks=3, days=4, hours=1),
    timedelta(weeks=3, days=4, hours=15),
    timedelta(weeks=2, days=2, hours=6),
    timedelta(weeks=1, days=5, hours=11),
    timedelta(days=2, hours=3),
)


def _fechas_demo_equivalentes(actual: datetime | None, esperada: datetime) -> bool:
    if actual is None:
        return False
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    return actual == esperada


def _aportes_demo_por_organizacion(oferta: OfertaAyuda, item: OfertaItem) -> dict[int, int]:
    """Distribuye determinísticamente un ítem demo entre sus participantes."""
    participantes = {oferta.organizacion_id, *(organizacion.id for organizacion in oferta.organizaciones)}
    participantes_ordenados = [oferta.organizacion_id] + sorted(
        participante for participante in participantes if participante != oferta.organizacion_id
    )
    if not oferta.es_conjunta or len(participantes_ordenados) < 2:
        return {oferta.organizacion_id: item.cantidad_ofrecida}

    base, resto = divmod(item.cantidad_ofrecida, len(participantes_ordenados))
    return {
        organizacion_id: base + (1 if indice < resto else 0)
        for indice, organizacion_id in enumerate(participantes_ordenados)
    }


def _resolver_equivalencias_cloud(db: Session, emergencias_demo: list[Emergencia]) -> bool:
    """Completa equivalencias nacionales demo sin crear IDs locales ficticios."""
    servicio = RecursosCloudService()
    hubo_cambios = False
    for emergencia in emergencias_demo:
        for lote in emergencia.lotes:
            nombre = normalizar_nombre_recurso(lote.tipo)
            if lote.tipo != nombre:
                lote.tipo = nombre
                hubo_cambios = True
            if lote.referencia_cloud is not None:
                continue
            try:
                recurso, _ = servicio.crear(
                    RecursoCloudCrear(nombre=nombre, descripcion=lote.descripcion)
                )
            except Exception as exc:
                # Una indisponibilidad de Cloud no debe abortar el arranque: se
                # conserva la demo local y se reintenta en el próximo inicio.
                logger.warning(
                    "Recursos demo: Cloud no disponible al resolver '%s'; "
                    "se reintentará en el próximo arranque (%s).",
                    nombre,
                    type(exc).__name__,
                )
                return hubo_cambios
            lote.referencia_cloud = LoteRecursoCloud(tipo_recurso_id=recurso.id)
            hubo_cambios = True
    return hubo_cambios

_DATOS_EMERGENCIAS = (
    ("Zona Norte", "Agua potable", NivelGravedad.ALTA, 9, EstadoEmergencia.ESPERA_OFERTAS, True),
    ("Zona Sur", "Kits de alimentos", NivelGravedad.MEDIA, 6, EstadoEmergencia.EN_PROCESO, True),
    ("Zona Este", "Mantas térmicas", NivelGravedad.CRITICA, 10, EstadoEmergencia.RESUELTA, True),
    ("Zona Oeste", "Medicamentos", NivelGravedad.ALTA, 8, EstadoEmergencia.ESPERA_LOTES, False),
    ("Zona Norte", "Generadores eléctricos", NivelGravedad.MEDIA, 5, EstadoEmergencia.ESPERA_OFERTAS, True),
    ("Zona Sur", "Pañales y artículos de higiene", NivelGravedad.BAJA, 3, EstadoEmergencia.EN_PROCESO, True),
    ("Zona Este", "Colchones", NivelGravedad.ALTA, 7, EstadoEmergencia.RESUELTA, True),
    ("Zona Oeste", "Kits de alimentos", NivelGravedad.CRITICA, 10, EstadoEmergencia.ESPERA_OFERTAS, True),
    ("Zona Norte", "Materiales de reparación", NivelGravedad.MEDIA, 4, EstadoEmergencia.ESPERA_LOTES, False),
    ("Zona Sur", "Botiquines", NivelGravedad.BAJA, 2, EstadoEmergencia.EN_PROCESO, True),
)


def sembrar_datos_demo(db: Session) -> None:
    """Completa la carga demo sólo en development y de forma idempotente."""
    if os.getenv("APP_ENV") != "development":
        return

    cantidad_existente = (
        db.query(func.count(Emergencia.id))
        .filter(Emergencia.descripcion_inicial.like(f"{PREFIJO_DEMO}%"))
        .scalar()
        or 0
    )
    hubo_cambios = False
    emergencias_demo = (
        db.query(Emergencia)
        .filter(Emergencia.descripcion_inicial.like(f"{PREFIJO_DEMO}%"))
        .all()
    )
    for emergencia in emergencias_demo:
        if "Agua y alimentos" in emergencia.descripcion_inicial:
            emergencia.descripcion_inicial = emergencia.descripcion_inicial.replace(
                "Agua y alimentos", "Kits de alimentos"
            )
            hubo_cambios = True
        for lote in emergencia.lotes:
            if lote.tipo == "Agua y alimentos":
                lote.tipo = "Kits de alimentos"
                hubo_cambios = True

    ahora = datetime.now(timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    creadas = []
    if cantidad_existente < CANTIDAD_EMERGENCIAS_DEMO:
        for indice in range(cantidad_existente, CANTIDAD_EMERGENCIAS_DEMO):
            zona, suministro, gravedad, prioridad, estado, publicada = _DATOS_EMERGENCIAS[indice]
            registro = ahora - _DESFASES_REGISTRO_DEMO[indice]
            emergencia = Emergencia(
                nivel_gravedad=gravedad,
                zona_afectada=zona,
                descripcion_inicial=(
                    f"{PREFIJO_DEMO} {indice + 1}: necesidad de {suministro.lower()}"
                ),
                fecha_hora_registro=registro,
                publicada=publicada,
                fecha_publicacion=registro + timedelta(hours=2) if publicada else None,
                estado=estado,
                prioridad=prioridad,
            )
            emergencia.lotes = [
                LoteNecesidad(
                    tipo=suministro,
                    cantidad=20 + indice * 5,
                    unidad="unidades",
                    descripcion=f"Lote demo para {zona.lower()}",
                ),
                LoteNecesidad(
                    tipo="Combustible" if indice % 2 == 0 else "Alimentos no perecederos",
                    cantidad=10 + indice,
                    unidad="cajas",
                    descripcion="Suministro complementario de demostración",
                ),
            ]
            creadas.append(emergencia)

        db.add_all(creadas)
        db.flush()
        hubo_cambios = True

    emergencias_demo = (
        db.query(Emergencia)
        .filter(Emergencia.descripcion_inicial.like(f"{PREFIJO_DEMO}%"))
        .order_by(Emergencia.id.asc())
        .all()
    )
    for indice, emergencia in enumerate(emergencias_demo):
        registro = ahora - _DESFASES_REGISTRO_DEMO[indice]
        if not _fechas_demo_equivalentes(
            emergencia.fecha_hora_registro, registro
        ):
            emergencia.fecha_hora_registro = registro
            hubo_cambios = True
        if emergencia.publicada:
            fecha_publicacion = registro + timedelta(hours=2)
            if not _fechas_demo_equivalentes(
                emergencia.fecha_publicacion, fecha_publicacion
            ):
                emergencia.fecha_publicacion = fecha_publicacion
                hubo_cambios = True

    # Los lotes demo deben poder participar en la evaluación nacional desde
    # el primer arranque. La operación es idempotente: reutiliza el catálogo
    # Cloud y solo persiste la equivalencia local que todavía falte.
    if _resolver_equivalencias_cloud(db, emergencias_demo):
        hubo_cambios = True

    nombres_organizaciones_demo = (
        "Organización de las Naciones Unidas",
        "UNICEF",
    )
    organizaciones_demo = (
        db.query(Organizacion)
        .filter(Organizacion.nombre.in_(nombres_organizaciones_demo))
        .order_by(Organizacion.id.asc())
        .all()
    )
    if organizaciones_demo:
        emergencia_convocatoria = next(
            (
                emergencia
                for emergencia in emergencias_demo
                if emergencia.publicada
                and emergencia.estado == EstadoEmergencia.ESPERA_OFERTAS
            ),
            None,
        )
        organizacion_onu = next(
            (
                organizacion
                for organizacion in organizaciones_demo
                if organizacion.nombre == "Organización de las Naciones Unidas"
            ),
            None,
        )
        for emergencia in emergencias_demo:
            if emergencia is emergencia_convocatoria:
                continue
            if emergencia.publicada and emergencia.estado in (
                EstadoEmergencia.EN_PROCESO,
                EstadoEmergencia.RESUELTA,
            ):
                continue
            ofertas_demo = (
                db.query(OfertaAyuda)
                .filter(
                    OfertaAyuda.emergencia_id == emergencia.id,
                    OfertaAyuda.observaciones
                    == "Oferta adjudicada de demostración para el dashboard",
                )
                .all()
            )
            for oferta in ofertas_demo:
                oferta.items.clear()
                oferta.organizaciones.clear()
                db.delete(oferta)
                hubo_cambios = True

        db.flush()
        emergencias_publicadas_demo = [
            emergencia
            for emergencia in emergencias_demo
            if emergencia.publicada
            and emergencia.estado
            in (EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA)
        ]
        for indice, emergencia in enumerate(emergencias_publicadas_demo):
            oferta = (
                db.query(OfertaAyuda)
                .filter(
                    OfertaAyuda.emergencia_id == emergencia.id,
                    OfertaAyuda.observaciones
                    == "Oferta adjudicada de demostración para el dashboard",
                )
                .order_by(OfertaAyuda.id.asc())
                .first()
            )
            if oferta is None:
                fecha_base = emergencia.fecha_publicacion or emergencia.fecha_hora_registro
                oferta = OfertaAyuda(
                    emergencia_id=emergencia.id,
                    fecha_hora_oferta=fecha_base + timedelta(hours=3),
                    observaciones="Oferta adjudicada de demostración para el dashboard",
                    adjudicada_en=fecha_base + timedelta(hours=6),
                )
                oferta.items = [
                    OfertaItem(
                        lote_necesidad=lote,
                        cantidad_ofrecida=lote.cantidad,
                        descripcion="Entrega demo adjudicada",
                        finalizado_en=(
                            fecha_base + timedelta(hours=8)
                            if emergencia.estado == EstadoEmergencia.RESUELTA
                            else None
                        ),
                    )
                    for lote in emergencia.lotes
                ]
                db.add(oferta)
                hubo_cambios = True

            fecha_hora_oferta = emergencia.fecha_publicacion + timedelta(hours=3)
            adjudicada_en = fecha_hora_oferta + timedelta(hours=3)
            if not _fechas_demo_equivalentes(
                oferta.fecha_hora_oferta, fecha_hora_oferta
            ):
                oferta.fecha_hora_oferta = fecha_hora_oferta
                hubo_cambios = True
            if not _fechas_demo_equivalentes(
                oferta.adjudicada_en, adjudicada_en
            ):
                oferta.adjudicada_en = adjudicada_en
                hubo_cambios = True
            fecha_finalizacion = (
                adjudicada_en + timedelta(hours=2)
                if emergencia.estado == EstadoEmergencia.RESUELTA
                else None
            )
            for item in oferta.items:
                if fecha_finalizacion is None:
                    finalizacion_coincide = item.finalizado_en is None
                else:
                    finalizacion_coincide = _fechas_demo_equivalentes(
                        item.finalizado_en, fecha_finalizacion
                    )
                if not finalizacion_coincide:
                    item.finalizado_en = fecha_finalizacion
                    hubo_cambios = True

            organizacion_titular = organizaciones_demo[indice % len(organizaciones_demo)]
            es_conjunta = len(organizaciones_demo) >= 2 and indice < 2
            organizaciones_oferta = (
                organizaciones_demo[:2] if es_conjunta else [organizacion_titular]
            )
            if oferta.organizacion_id != organizacion_titular.id:
                oferta.organizacion_id = organizacion_titular.id
                hubo_cambios = True
            if oferta.es_conjunta != es_conjunta:
                oferta.es_conjunta = es_conjunta
                hubo_cambios = True
            ids_actuales = {organizacion.id for organizacion in oferta.organizaciones}
            ids_esperados = {organizacion.id for organizacion in organizaciones_oferta}
            if ids_actuales != ids_esperados:
                oferta.organizaciones = organizaciones_oferta
                hubo_cambios = True

            for item in oferta.items:
                aportes_esperados = _aportes_demo_por_organizacion(oferta, item)
                aportes_actuales = {
                    aporte.organizacion_id: aporte.cantidad
                    for aporte in item.aportes
                }
                if aportes_actuales != aportes_esperados:
                    item.aportes = [
                        AporteOfertaItem(
                            organizacion_id=organizacion_id,
                            cantidad=cantidad,
                        )
                        for organizacion_id, cantidad in aportes_esperados.items()
                    ]
                    hubo_cambios = True

        if emergencia_convocatoria is not None and organizacion_onu is not None:
            ofertas_convocatoria = (
                db.query(OfertaAyuda)
                .filter(
                    OfertaAyuda.emergencia_id == emergencia_convocatoria.id,
                    OfertaAyuda.observaciones
                    == "Oferta adjudicada de demostración para el dashboard",
                )
                .order_by(OfertaAyuda.id.asc())
                .all()
            )
            oferta_convocatoria = ofertas_convocatoria[0] if ofertas_convocatoria else None
            for oferta_duplicada in ofertas_convocatoria[1:]:
                oferta_duplicada.items.clear()
                oferta_duplicada.organizaciones.clear()
                db.delete(oferta_duplicada)
                hubo_cambios = True

            if oferta_convocatoria is None:
                oferta_convocatoria = OfertaAyuda(
                    emergencia_id=emergencia_convocatoria.id,
                    fecha_hora_oferta=(
                        emergencia_convocatoria.fecha_publicacion
                        + timedelta(hours=3)
                    ),
                    observaciones="Oferta adjudicada de demostración para el dashboard",
                    adjudicada_en=None,
                    es_conjunta=False,
                )
                db.add(oferta_convocatoria)
                hubo_cambios = True

            fecha_hora_oferta = (
                emergencia_convocatoria.fecha_publicacion + timedelta(hours=3)
            )
            if not _fechas_demo_equivalentes(
                oferta_convocatoria.fecha_hora_oferta, fecha_hora_oferta
            ):
                oferta_convocatoria.fecha_hora_oferta = fecha_hora_oferta
                hubo_cambios = True
            if oferta_convocatoria.adjudicada_en is not None:
                oferta_convocatoria.adjudicada_en = None
                hubo_cambios = True
            if oferta_convocatoria.organizacion_id != organizacion_onu.id:
                oferta_convocatoria.organizacion_id = organizacion_onu.id
                hubo_cambios = True
            if oferta_convocatoria.es_conjunta:
                oferta_convocatoria.es_conjunta = False
                hubo_cambios = True
            if {
                organizacion.id for organizacion in oferta_convocatoria.organizaciones
            } != {organizacion_onu.id}:
                oferta_convocatoria.organizaciones = [organizacion_onu]
                hubo_cambios = True

            lotes_por_id = {
                lote.id: lote for lote in emergencia_convocatoria.lotes
            }
            lotes_cubiertos = set()
            for item in list(oferta_convocatoria.items):
                lote = lotes_por_id.get(item.lote_necesidad_id)
                if lote is None or lote.id in lotes_cubiertos:
                    oferta_convocatoria.items.remove(item)
                    db.delete(item)
                    hubo_cambios = True
                    continue
                lotes_cubiertos.add(lote.id)
                if item.cantidad_ofrecida != lote.cantidad:
                    item.cantidad_ofrecida = lote.cantidad
                    hubo_cambios = True
                if item.descripcion != "Entrega demo para convocatoria abierta":
                    item.descripcion = "Entrega demo para convocatoria abierta"
                    hubo_cambios = True
                if item.finalizado_en is not None:
                    item.finalizado_en = None
                    hubo_cambios = True
            for lote in emergencia_convocatoria.lotes:
                if lote.id not in lotes_cubiertos:
                    oferta_convocatoria.items.append(
                        OfertaItem(
                            lote_necesidad=lote,
                            cantidad_ofrecida=lote.cantidad,
                            descripcion="Entrega demo para convocatoria abierta",
                        )
                    )
                    hubo_cambios = True

        db.flush()
        ofertas_demo = (
            db.query(OfertaAyuda)
            .filter(
                OfertaAyuda.emergencia_id.in_(
                    [
                        emergencia.id
                        for emergencia in emergencias_publicadas_demo
                    ]
                ),
                OfertaAyuda.observaciones
                == "Oferta adjudicada de demostración para el dashboard",
                OfertaAyuda.adjudicada_en.is_not(None),
            )
            .all()
        )
        for organizacion in organizaciones_demo:
            cantidades_por_tipo = {}
            unidades_por_tipo = {}
            for oferta in ofertas_demo:
                participa = oferta.organizacion_id == organizacion.id or any(
                    socia.id == organizacion.id
                    for socia in oferta.organizaciones
                )
                if not participa:
                    continue
                for item in oferta.items:
                    tipo = item.lote_necesidad.tipo
                    aporte = _aportes_demo_por_organizacion(oferta, item).get(
                        organizacion.id,
                        0,
                    )
                    if aporte <= 0:
                        continue
                    cantidades_por_tipo[tipo] = (
                        cantidades_por_tipo.get(tipo, 0) + aporte
                    )
                    unidades_por_tipo.setdefault(
                        tipo, item.lote_necesidad.unidad or "unidades"
                    )

            recursos_demo = (
                db.query(RecursoInventario)
                .filter(
                    RecursoInventario.organizacion_id == organizacion.id,
                    RecursoInventario.descripcion.like(f"{PREFIJO_DEMO}%"),
                )
                .all()
            )
            for recurso in recursos_demo:
                tipo_normalizado = normalizar_nombre_recurso(recurso.tipo)
                if recurso.tipo != tipo_normalizado:
                    recurso.tipo = tipo_normalizado
                    hubo_cambios = True
            descripcion_derivada = (
                f"{PREFIJO_DEMO} Inventario derivado de ofertas adjudicadas"
            )
            for recurso in list(recursos_demo):
                if (
                    recurso.descripcion == descripcion_derivada
                    and recurso.tipo not in cantidades_por_tipo
                ):
                    db.delete(recurso)
                    recursos_demo.remove(recurso)
                    hubo_cambios = True

            for tipo, cantidad in cantidades_por_tipo.items():
                descripcion = descripcion_derivada
                recurso = next(
                    (
                        recurso
                        for recurso in recursos_demo
                        if recurso.tipo == tipo
                        and recurso.descripcion == descripcion
                    ),
                    None,
                )
                if recurso is None:
                    recurso = RecursoInventario(
                        organizacion_id=organizacion.id,
                        tipo=tipo,
                        cantidad_total=cantidad,
                        unidad=unidades_por_tipo[tipo],
                        descripcion=descripcion,
                    )
                    db.add(recurso)
                    recursos_demo.append(recurso)
                    hubo_cambios = True
                else:
                    if recurso.cantidad_total != cantidad:
                        recurso.cantidad_total = cantidad
                        hubo_cambios = True
                    if recurso.unidad != unidades_por_tipo[tipo]:
                        recurso.unidad = unidades_por_tipo[tipo]
                        hubo_cambios = True

            tipos_excedentes = []
            for tipo in (
                "Carpas",
                "Linternas",
                "Radios de comunicación",
                "Equipos de cocina",
            ):
                if tipo not in cantidades_por_tipo:
                    tipos_excedentes.append(tipo)
                if len(tipos_excedentes) == 2:
                    break
            for indice, tipo in enumerate(tipos_excedentes, start=1):
                descripcion = f"{PREFIJO_DEMO} Excedente {indice}"
                recurso = next(
                    (
                        recurso
                        for recurso in recursos_demo
                        if recurso.descripcion == descripcion
                    ),
                    None,
                )
                cantidad = 25 + (indice * 5)
                if recurso is None:
                    recurso = RecursoInventario(
                        organizacion_id=organizacion.id,
                        tipo=tipo,
                        cantidad_total=cantidad,
                        unidad="unidades",
                        descripcion=descripcion,
                    )
                    db.add(recurso)
                    recursos_demo.append(recurso)
                    hubo_cambios = True
                else:
                    if recurso.tipo != tipo:
                        recurso.tipo = tipo
                        hubo_cambios = True
                    if recurso.cantidad_total != cantidad:
                        recurso.cantidad_total = cantidad
                        hubo_cambios = True
                    if recurso.unidad != "unidades":
                        recurso.unidad = "unidades"
                        hubo_cambios = True

    if cantidad_existente < CANTIDAD_EMERGENCIAS_DEMO or hubo_cambios:
        db.commit()

