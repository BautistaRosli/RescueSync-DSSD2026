"""Carga idempotente de datos de demostración para desarrollo."""

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
    Organizacion,
)

PREFIJO_DEMO = "[DEMO DASHBOARD]"
CANTIDAD_EMERGENCIAS_DEMO = 10

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

    if cantidad_existente >= CANTIDAD_EMERGENCIAS_DEMO:
        if hubo_cambios:
            db.commit()
        return

    ahora = datetime.now(timezone.utc)
    organizaciones = db.query(Organizacion).order_by(Organizacion.id.asc()).all()
    creadas = []
    for indice in range(cantidad_existente, CANTIDAD_EMERGENCIAS_DEMO):
        zona, suministro, gravedad, prioridad, estado, publicada = _DATOS_EMERGENCIAS[indice]
        registro = ahora - timedelta(days=indice + 1, hours=indice)
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

    if organizaciones:
        for indice, emergencia in enumerate(creadas):
            if not emergencia.publicada or emergencia.estado not in (
                EstadoEmergencia.ESPERA_OFERTAS,
                EstadoEmergencia.EN_PROCESO,
                EstadoEmergencia.RESUELTA,
            ):
                continue
            organizacion = organizaciones[indice % len(organizaciones)]
            oferta = OfertaAyuda(
                emergencia_id=emergencia.id,
                organizacion_id=organizacion.id,
                fecha_hora_oferta=emergencia.fecha_publicacion + timedelta(hours=3),
                observaciones="Oferta adjudicada de demostración para el dashboard",
                adjudicada_en=emergencia.fecha_publicacion + timedelta(hours=6),
            )
            oferta.items = [
                OfertaItem(
                    lote_necesidad=lote,
                    cantidad_ofrecida=lote.cantidad,
                    descripcion="Entrega demo adjudicada",
                    finalizado_en=(
                        emergencia.fecha_publicacion + timedelta(hours=8)
                        if emergencia.estado == EstadoEmergencia.RESUELTA
                        else None
                    ),
                )
                for lote in emergencia.lotes
            ]
            db.add(oferta)

    db.commit()

