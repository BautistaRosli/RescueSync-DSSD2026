"""Proyección de ofertas locales; nunca deduce equivalencias nacionales."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..dto.solicitud_evaluacion_dto import SolicitudEvaluacion
from ..models import AporteOfertaItem, LoteRecursoCloud, OrganizacionCloud
from ..repositories import OfertaRepository
from .emergencias_service import EmergenciaService


class SolicitudEvaluacionService:
    def obtener(self, db: Session, emergencia_id: int) -> SolicitudEvaluacion:
        emergencia = EmergenciaService().obtener_emergencia_entidad(db, emergencia_id)
        lotes = sorted(emergencia.lotes, key=lambda lote: lote.id)
        if not lotes:
            raise HTTPException(409, "La emergencia no tiene lotes: cargue al menos uno antes de evaluar")
        tipos = dict(db.query(LoteRecursoCloud.lote_id, LoteRecursoCloud.tipo_recurso_id)
                     .filter(LoteRecursoCloud.lote_id.in_([lote.id for lote in lotes])).all())
        for lote in lotes:
            if lote.id not in tipos:
                raise HTTPException(409, f"Falta tipo_recurso_id nacional del lote {lote.id}: complete su equivalencia antes de evaluar")
        ofertas = OfertaRepository().listar_de_emergencia(db, emergencia_id)
        organizaciones = {oferta.organizacion_id for oferta in ofertas}
        for oferta in ofertas:
            organizaciones.update(ong.id for ong in oferta.organizaciones)
        nacionales = dict(db.query(OrganizacionCloud.organizacion_id, OrganizacionCloud.ong_id)
                           .filter(OrganizacionCloud.organizacion_id.in_(organizaciones)).all())
        if len(set(nacionales.values())) != len(nacionales):
            raise HTTPException(409, "Hay organizaciones locales con el mismo ong_id nacional: verifique sus vinculaciones con Cloud antes de evaluar")
        ids_items = [item.id for oferta in ofertas for item in oferta.items]
        aportes_por_item = {}
        for aporte in db.query(AporteOfertaItem).filter(AporteOfertaItem.item_id.in_(ids_items)).all():
            aportes_por_item.setdefault(aporte.item_id, []).append(aporte)

        def ong_nacional(organizacion_id):
            if organizacion_id not in nacionales:
                raise HTTPException(409, f"Falta ong_id nacional de la organización {organizacion_id}: requiere una vinculación verificada con Cloud")
            return nacionales[organizacion_id]

        filas = []
        for oferta in ofertas:
            responsable = ong_nacional(oferta.organizacion_id)
            participantes = {ong.id for ong in oferta.organizaciones} | {oferta.organizacion_id}
            conjunta = oferta.es_conjunta or len(participantes) > 1
            for item in sorted(oferta.items, key=lambda item: item.lote_necesidad_id):
                lote_id = item.lote_necesidad_id
                if lote_id not in tipos:
                    raise HTTPException(409, f"El lote {lote_id} de la oferta {oferta.id} no pertenece a la emergencia")
                if conjunta:
                    aportes = aportes_por_item.get(item.id, [])
                    if (not aportes or len(participantes) < 2
                            or any(aporte.organizacion_id not in participantes for aporte in aportes)
                            or sum(aporte.cantidad for aporte in aportes) != item.cantidad_ofrecida):
                        raise HTTPException(409, f"Faltan aportes válidos en la oferta {oferta.id}, lote {lote_id}: declare el reparto real entre participantes")
                    cantidades = [(ong_nacional(a.organizacion_id), a.cantidad) for a in aportes]
                else:
                    cantidades = [(responsable, item.cantidad_ofrecida)]
                filas.append({"oferta_id": oferta.id, "lote_id": lote_id,
                              "ong_responsable_id": responsable,
                              "aportes": [{"ong_id": nacional,
                                           "items": [{"tipo_recurso_id": tipos[lote_id], "cantidad": cantidad}]}
                                          for nacional, cantidad in sorted(cantidades)]})
        return SolicitudEvaluacion(
            emergencia_id=emergencia_id,
            lotes=[{"lote_id": lote.id, "tipo_recurso_id": tipos[lote.id],
                    "cantidad_requerida": lote.cantidad} for lote in lotes],
            ofertas=filas,
        )
