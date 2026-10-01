import logging
from datetime import datetime

from .client import EmailClientError, email_client

logger = logging.getLogger(__name__)


def notificar_nueva_emergencia(
    destinatarios: list[str],
    emergencia_id: int,
    nivel_gravedad: str,
    zona_afectada: str,
    descripcion_inicial: str,
    fecha_hora_registro: datetime,
) -> None:
    """Avisa al Centro Coordinador que se registro una emergencia nueva.

    Nunca propaga errores: la emergencia ya quedo creada y una falla de
    correo no debe revertirla.
    """
    if not destinatarios:
        logger.info(
            "No hay usuarios activos con rol CENTRO_COORDINADOR: "
            f"no se notifico la emergencia {emergencia_id}"
        )
        return

    asunto = f"[RescueSync] Nueva emergencia registrada #{emergencia_id}"
    cuerpo = (
        "Se registro una nueva emergencia en la plataforma RescueSync.\n\n"
        f"Id: {emergencia_id}\n"
        f"Nivel de gravedad: {nivel_gravedad}\n"
        f"Zona afectada: {zona_afectada}\n"
        f"Fecha y hora de registro: {fecha_hora_registro}\n\n"
        f"Descripcion inicial:\n{descripcion_inicial}\n"
    )

    if not email_client.configurado:
        logger.info(
            "SMTP no configurado, se loguea el email en lugar de enviarlo. "
            f"destinatarios={destinatarios}, asunto={asunto!r}, cuerpo:\n{cuerpo}"
        )
        return

    try:
        email_client.enviar(destinatarios, asunto, cuerpo)
    except EmailClientError as exc:
        logger.error(f"Fallo la notificacion por email de la emergencia: {exc}")


def notificar_adjudicacion(
    destinatarios: list[str],
    oferta_id: int,
    emergencia_id: int,
    zona_afectada: str,
    lotes_adjudicados: list[str],
    fecha_hora_adjudicacion: datetime,
) -> None:
    """Avisa a la ONG que su oferta fue adjudicada para una emergencia.

    Nunca propaga errores: la adjudicacion ya fue resuelta y una falla de
    correo no debe hacerla fallar.
    """
    if not destinatarios:
        logger.info(
            "No hay destinatarios para la ONG de la oferta: "
            f"no se notifico la adjudicacion de la oferta {oferta_id}"
        )
        return

    asunto = (
        f"[RescueSync] Oferta #{oferta_id} adjudicada "
        f"para la emergencia #{emergencia_id}"
    )
    detalle_lotes = "\n".join(lotes_adjudicados)
    cuerpo = (
        "Su oferta de ayuda fue adjudicada en la plataforma RescueSync.\n\n"
        f"Id de oferta: {oferta_id}\n"
        f"Id de emergencia: {emergencia_id}\n"
        f"Zona afectada: {zona_afectada}\n"
        f"Fecha y hora de adjudicacion: {fecha_hora_adjudicacion}\n\n"
        f"Lotes adjudicados:\n{detalle_lotes}\n"
    )

    if not email_client.configurado:
        logger.info(
            "SMTP no configurado, se loguea el email en lugar de enviarlo. "
            f"destinatarios={destinatarios}, asunto={asunto!r}, cuerpo:\n{cuerpo}"
        )
        return

    try:
        email_client.enviar(destinatarios, asunto, cuerpo)
    except EmailClientError as exc:
        logger.error(f"Fallo la notificacion por email de la adjudicacion: {exc}")
