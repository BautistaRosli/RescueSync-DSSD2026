"""Autorización por rol y alcance de los recursos de la API."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Usuario
from .emergencias_service import EmergenciaService
from .lotes_service import LoteService
from .ofertas_service import OfertaService

OPERADOR = "OPERADOR_MUNICIPAL"
COORDINADOR = "CENTRO_COORDINADOR"
ONG = "REPRESENTANTE_ONG"
AUDITOR = "DIRECTOR_AUDITOR"


def denegar() -> None:
    raise HTTPException(status_code=403, detail="No tiene permiso para acceder a este recurso")


def filtrar_publicada(usuario: Usuario, publicada: bool | None) -> bool | None:
    alcance = {OPERADOR: False, ONG: True}.get(usuario.rol.nombre)
    if alcance is not None:
        if publicada is not None and publicada != alcance:
            denegar()
        return alcance
    return publicada


def verificar_emergencia(db: Session, usuario: Usuario, emergencia_id: int) -> None:
    emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id)
    filtrar_publicada(usuario, emergencia.publicada)


def verificar_lote(db: Session, usuario: Usuario, lote_id: int) -> None:
    lote = LoteService().obtener_lote(db, lote_id)
    verificar_emergencia(db, usuario, lote.emergencia_id)


def filtrar_organizacion(usuario: Usuario, organizacion_id: int | None = None) -> int | None:
    if usuario.rol.nombre == ONG:
        if usuario.organizacion_id is None:
            denegar()
        if organizacion_id is not None and organizacion_id != usuario.organizacion_id:
            denegar()
        return usuario.organizacion_id
    return organizacion_id


def verificar_oferta(db: Session, usuario: Usuario, oferta_id: int) -> None:
    oferta = OfertaService().obtener_oferta(db, oferta_id)
    filtrar_organizacion(usuario, oferta.organizacion_id)
