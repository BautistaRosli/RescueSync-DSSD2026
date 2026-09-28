import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")


class EmailClientError(Exception):
    pass


class EmailClient:
    """Cliente SMTP minimo para notificaciones por correo.

    Si no hay SMTP_HOST configurado no intenta conectar: el envio queda en
    modo log, para no romper los flujos en entornos sin servidor de correo.
    """

    @property
    def configurado(self) -> bool:
        return bool(SMTP_HOST)

    def enviar(
        self, destinatarios: list[str], asunto: str, cuerpo: str
    ) -> None:
        if not self.configurado:
            logger.info(
                "SMTP no configurado: email no enviado. "
                f"destinatarios={destinatarios}, asunto={asunto!r}"
            )
            return

        mensaje = EmailMessage()
        mensaje["From"] = SMTP_FROM or SMTP_USER
        mensaje["To"] = ", ".join(destinatarios)
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo)

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.ehlo()
                if smtp.has_extn("starttls"):
                    smtp.starttls()
                    smtp.ehlo()
                if SMTP_USER:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(mensaje)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailClientError(f"No se pudo enviar el email: {exc}") from exc

        logger.info(
            f"Email enviado a {destinatarios} con asunto {asunto!r}"
        )


email_client = EmailClient()
