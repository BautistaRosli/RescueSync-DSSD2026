from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dto.reportes_dto import (
    CoberturaLoteReporte,
    CoberturaLotesReporte,
    ConsorciosReporte,
    DemandaOfertaReporte,
    EmergenciaReporte,
    ProyectoReporte,
    RankingONGReporte,
    SuministroMovilizadoReporte,
    TiempoAdjudicacionReporte,
    TiempoPublicacionReporte,
)
from ..models import Emergencia, EstadoEmergencia, LoteNecesidad, OfertaAyuda, OfertaItem, Organizacion


def _horas(inicio: datetime, fin: datetime) -> float:
    return (fin - inicio).total_seconds() / 3600


class ReportesService:
    def _datos(self, db: Session):
        emergencias = list(db.scalars(select(Emergencia)).all())
        lotes = list(db.scalars(select(LoteNecesidad)).all())
        ofertas = list(db.scalars(select(OfertaAyuda)).all())
        items = list(db.scalars(select(OfertaItem)).all())
        organizaciones = list(db.scalars(select(Organizacion)).all())
        return emergencias, lotes, ofertas, items, organizaciones

    @staticmethod
    def _ofertas_adjudicadas(ofertas):
        return [oferta for oferta in ofertas if oferta.adjudicada_en is not None]

    def emergencias(self, db: Session) -> list[EmergenciaReporte]:
        emergencias, *_ = self._datos(db)
        conteos = defaultdict(int)
        for emergencia in emergencias:
            conteos[(emergencia.estado, emergencia.nivel_gravedad)] += 1
        return [EmergenciaReporte(estado=estado, nivel_gravedad=gravedad, cantidad=cantidad)
                for (estado, gravedad), cantidad in sorted(conteos.items())]

    def suministros_movilizados(self, db: Session) -> list[SuministroMovilizadoReporte]:
        _, lotes, ofertas, items, _ = self._datos(db)
        por_lote = {lote.id: lote for lote in lotes}
        adjudicadas = {oferta.id: oferta for oferta in self._ofertas_adjudicadas(ofertas)}
        conteos = defaultdict(int)
        for item in items:
            oferta = adjudicadas.get(item.oferta_id)
            lote = por_lote.get(item.lote_necesidad_id)
            if oferta and lote:
                conteos[(oferta.adjudicada_en.strftime("%Y-%m"), lote.tipo)] += item.cantidad_ofrecida
        return [SuministroMovilizadoReporte(mes=mes, tipo_recurso=tipo, cantidad_adjudicada=cantidad)
                for (mes, tipo), cantidad in sorted(conteos.items())]

    def consorcios(self, db: Session) -> ConsorciosReporte:
        _, _, ofertas, _, _ = self._datos(db)
        adjudicadas = self._ofertas_adjudicadas(ofertas)
        conjuntas = sum(1 for oferta in adjudicadas if oferta.es_conjunta)
        total = len(adjudicadas)
        return ConsorciosReporte(total_ofertas_adjudicadas=total, ofertas_conjuntas=conjuntas,
                                 porcentaje_consorcios=(conjuntas * 100 / total) if total else 0)

    def proyectos(self, db: Session) -> list[ProyectoReporte]:
        emergencias, _, ofertas, items, _ = self._datos(db)
        adjudicadas = self._ofertas_adjudicadas(ofertas)
        ids = {oferta.id for oferta in adjudicadas}
        por_emergencia = defaultdict(list)
        for oferta in adjudicadas:
            por_emergencia[oferta.emergencia_id].append(oferta.id)
        filas = []
        for emergencia in emergencias:
            ids_ofertas = set(por_emergencia.get(emergencia.id, []))
            items_emergencia = [item for item in items if item.oferta_id in ids_ofertas]
            finalizados = sum(item.finalizado_en is not None for item in items_emergencia)
            if ids_ofertas:
                filas.append(ProyectoReporte(emergencia_id=emergencia.id, zona_afectada=emergencia.zona_afectada,
                    items_totales=len(items_emergencia), items_finalizados=finalizados,
                    items_pendientes=len(items_emergencia) - finalizados,
                    resuelta=emergencia.estado == EstadoEmergencia.RESUELTA))
        return filas

    def cobertura_lotes(self, db: Session) -> CoberturaLotesReporte:
        _, lotes, ofertas, items, _ = self._datos(db)
        adjudicadas = {oferta.id for oferta in self._ofertas_adjudicadas(ofertas)}
        ofrecido = defaultdict(int)
        for item in items:
            if item.oferta_id in adjudicadas:
                ofrecido[item.lote_necesidad_id] += item.cantidad_ofrecida
        filas = [CoberturaLoteReporte(lote_id=lote.id, emergencia_id=lote.emergencia_id, tipo_recurso=lote.tipo,
                    cantidad_requerida=lote.cantidad, cantidad_ofrecida=ofrecido[lote.id],
                    porcentaje_cobertura=(ofrecido[lote.id] * 100 / lote.cantidad) if lote.cantidad else 0)
                 for lote in lotes]
        return CoberturaLotesReporte(lotes=filas, lotes_sin_cubrir=[fila for fila in filas if fila.porcentaje_cobertura < 100])

    def tiempo_publicacion(self, db: Session) -> TiempoPublicacionReporte:
        emergencias, *_ = self._datos(db)
        valores = [_horas(e.fecha_hora_registro, e.fecha_publicacion) for e in emergencias if e.fecha_hora_registro and e.fecha_publicacion]
        return TiempoPublicacionReporte(promedio_horas=sum(valores) / len(valores) if valores else 0,
                                        minimo_horas=min(valores) if valores else 0, maximo_horas=max(valores) if valores else 0)

    def tiempo_adjudicacion(self, db: Session) -> TiempoAdjudicacionReporte:
        emergencias, _, ofertas, _, _ = self._datos(db)
        por_id = {e.id: e for e in emergencias}
        valores = [_horas(por_id[o.emergencia_id].fecha_publicacion, o.adjudicada_en)
                   for o in ofertas if o.adjudicada_en and por_id.get(o.emergencia_id) and por_id[o.emergencia_id].fecha_publicacion]
        return TiempoAdjudicacionReporte(promedio_horas=sum(valores) / len(valores) if valores else 0)

    def ranking_ongs(self, db: Session) -> list[RankingONGReporte]:
        _, _, ofertas, items, organizaciones = self._datos(db)
        filas = []
        for organizacion in organizaciones:
            titulares = [o for o in ofertas if o.organizacion_id == organizacion.id]
            participadas = [o for o in ofertas if organizacion in o.organizaciones]
            todas = {o.id: o for o in titulares + participadas}.values()
            adjudicadas = [o for o in todas if o.adjudicada_en is not None]
            ids = {o.id for o in adjudicadas}
            filas.append(RankingONGReporte(organizacion_id=organizacion.id, organizacion_nombre=organizacion.nombre,
                ofertas_presentadas=len(titulares), ofertas_adjudicadas=len(adjudicadas),
                participaciones_consorcios=sum(organizacion in o.organizaciones for o in adjudicadas if o.es_conjunta),
                actividades_finalizadas=sum(i.finalizado_en is not None for i in items if i.oferta_id in ids)))
        return filas

    def demanda_oferta(self, db: Session) -> list[DemandaOfertaReporte]:
        _, lotes, ofertas, items, _ = self._datos(db)
        adjudicadas = {o.id for o in self._ofertas_adjudicadas(ofertas)}
        pedidos = defaultdict(int)
        ofrecidos = defaultdict(int)
        for lote in lotes:
            pedidos[lote.tipo] += lote.cantidad
        por_lote = {lote.id: lote.tipo for lote in lotes}
        for item in items:
            if item.oferta_id in adjudicadas and item.lote_necesidad_id in por_lote:
                ofrecidos[por_lote[item.lote_necesidad_id]] += item.cantidad_ofrecida
        return [DemandaOfertaReporte(tipo_recurso=tipo, cantidad_pedida=pedidos[tipo], cantidad_ofrecida=ofrecidos[tipo])
                for tipo in sorted(set(pedidos) | set(ofrecidos))]
