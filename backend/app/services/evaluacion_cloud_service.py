"""Conserva la evaluación recibida bajo el bloqueo municipal de emergencia."""

import json

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import EstadoEmergencia, EvaluacionCloud
from .emergencias_service import EmergenciaService


class EvaluacionCloudService:
    @staticmethod
    def ultima(db: Session, emergencia_id: int):
        return (db.query(EvaluacionCloud).filter_by(emergencia_id=emergencia_id)
                .order_by(EvaluacionCloud.id.desc()).populate_existing().first())

    @classmethod
    def invalidar(cls, db: Session, emergencia_id: int):
        ronda = cls.ultima(db, emergencia_id)
        if ronda is not None:
            ronda.vigente = False

    @classmethod
    def obtener(cls, db: Session, emergencia_id: int, caso_id: int):
        ronda = cls.ultima(db, emergencia_id)
        if ronda is None:
            return None  # Sólo las convocatorias legacy consultan la variable Bonita.
        if not ronda.vigente or ronda.caso_id != str(caso_id) or ronda.evaluacion_json is None:
            raise HTTPException(409, "La evaluación local de la ronda actual aún no está disponible")
        return json.loads(ronda.evaluacion_json)

    def recibir(self, db: Session, emergencia_id: int, datos) -> None:
        try:
            emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id, bloquear=True)
            ronda = self.ultima(db, emergencia_id)
            evaluacion = datos.evaluacion
            if (ronda is None or not ronda.vigente or ronda.solicitud_id != datos.solicitud_id
                    or ronda.caso_id != str(datos.caso_id)
                    or emergencia.bonita_case_id != str(datos.caso_id)
                    or evaluacion["emergencia_id"] != emergencia_id):
                raise HTTPException(409, "La evaluación no corresponde al caso y ronda vigentes")
            if ronda.evaluacion_json is not None:
                if (json.dumps(json.loads(ronda.evaluacion_json), sort_keys=True)
                        == json.dumps(evaluacion, sort_keys=True)):
                    return
                raise HTTPException(409, "La ronda ya tiene una evaluación diferente")
            from .curso_accion_service import CursoAccionService
            if emergencia.estado != EstadoEmergencia.ESPERANDO_ADJUDICACION:
                raise HTTPException(409, "La emergencia no está esperando esta evaluación")
            CursoAccionService.validar_retroceso(db, emergencia_id)
            solicitud = json.loads(ronda.solicitud_json)
            esperados = {(fila["oferta_id"], fila["lote_id"]): sum(
                item["cantidad"] for aporte in fila["aportes"] for item in aporte["items"]
            ) for fila in solicitud["ofertas"]}
            recibidos = set()
            for fila in evaluacion["resultados"]:
                par = (fila["oferta_id"], fila["lote_id"])
                if (par in recibidos or par not in esperados
                        or fila["cantidad_ofrecida"] != esperados[par]
                        or fila["cantidad_verificada"] > esperados[par]
                        or any(capacidad["cantidad_verificada"] > capacidad["cantidad_ofrecida"]
                               for participante in fila["participantes"]
                               for capacidad in participante["capacidades_habilitadas"])):
                    raise HTTPException(409, "La evaluación contiene pares o cantidades ajenos a la solicitud")
                recibidos.add(par)
            if recibidos != set(esperados):
                raise HTTPException(409, "La evaluación no contiene todos los pares solicitados")
            ronda.evaluacion_json = json.dumps(evaluacion, ensure_ascii=False, allow_nan=False)
            db.commit()
        except SQLAlchemyError:
            raise HTTPException(503, "No se pudo conservar la evaluación; vuelva a intentar") from None
        finally:
            db.rollback()
