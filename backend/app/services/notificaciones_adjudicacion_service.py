"""Entrega recuperable de los avisos creados al confirmar una selección."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select

from ..database import SessionLocal
from ..models import AvisoAdjudicacion, OfertaAyuda
from . import ofertas_service

logger = logging.getLogger(__name__)


def _reloj_base(db):
    # now() en PostgreSQL fija la hora al inicio de la transacción. El reloj
    # real permite esperar el backoff completo después de un SMTP lento.
    return func.clock_timestamp() if db.get_bind().dialect.name == "postgresql" else func.now()


def procesar_aviso_pendiente(sesiones=SessionLocal) -> bool:
    """Procesa un intento con sesión propia y lock exclusivo sólo del aviso.

    PostgreSQL omite filas tomadas por otro consumidor. SMTP ocurre después
    del commit de confirmación; el lock dura hasta persistir éxito o reintento.
    Si SMTP acepta y el proceso cae antes del commit, podrá repetirse el correo.
    """
    with sesiones() as db, db.begin():
        aviso = db.scalar(
            select(AvisoAdjudicacion)
            .where(AvisoAdjudicacion.enviada_en.is_(None),
                   AvisoAdjudicacion.proximo_intento_en <= _reloj_base(db))
            .order_by(AvisoAdjudicacion.proximo_intento_en, AvisoAdjudicacion.oferta_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if aviso is None:
            return False
        aviso.intentos += 1
        try:
            oferta = db.get(OfertaAyuda, aviso.oferta_id)
            datos = ofertas_service.OfertaService()._datos_notificacion_adjudicacion(
                db, oferta, aviso.creada_en
            )
            ofertas_service.notificar_adjudicacion(*datos, estricto=True)
        except Exception as exc:
            # Sin destinatarios o SMTP disponible queda pendiente y recuperable.
            espera = min(30 * 2 ** min(aviso.intentos - 1, 7), 3600)
            aviso.proximo_intento_en = db.scalar(select(_reloj_base(db))) + timedelta(seconds=espera)
            logger.warning("Aviso pendiente oferta=%s intento=%s causa=%s",
                           aviso.oferta_id, aviso.intentos, type(exc).__name__)
        else:
            aviso.enviada_en = db.scalar(select(_reloj_base(db)))
            logger.info("Aviso entregado oferta=%s intento=%s", aviso.oferta_id, aviso.intentos)
    return True


async def consumir_avisos(detener: asyncio.Event, sesiones=SessionLocal) -> None:
    """Consulta al arrancar y cada cinco segundos sin bloquear el event loop."""
    while not detener.is_set():
        try:
            procesado = await asyncio.to_thread(procesar_aviso_pendiente, sesiones)
        except Exception as exc:
            logger.error("No se pudo procesar avisos causa=%s", type(exc).__name__)
            procesado = False
        if not procesado and not detener.is_set():
            try:
                await asyncio.wait_for(detener.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
