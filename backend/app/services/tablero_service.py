"""Tablero del Auditor: una sola función para la pantalla y la exportación.

Cruza la base local (emergencias, ofertas, cierres), la evaluación del
Sistema Nacional guardada localmente (Cloud) y el estado de los casos en
Bonita. Todas las fechas se comparan en UTC sin zona.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from ..dto.tablero_dto import (
    BonitaTablero, CantidadPorUnidad, FilaEstadoGravedad, FilaEvolucion, FilaRankingONG,
    FiltrosAplicados, FuenteFechaCierre, IndicadorConsorcios, IndicadorConteo,
    IndicadorEstadoGravedad, IndicadorEvolucion, IndicadorPromedioHoras,
    IndicadorPromedioValor, IndicadorProyectos, IndicadorRankingONG,
    IndicadorRecursosPorLote, IndicadorResolucion, IndicadorTotalesRecursos,
    ProyectosTablero, ProyectoTablero, RecursoPorLote, RecursosTablero, ResumenTablero,
    TableroRespuesta, TiempoEtapa, TotalRecursoMes, VerificacionCaso,
)
from ..integrations.bonita.client import BonitaClientError, bonita_client
from ..models import (
    AvisoAdjudicacion, CierreEmergencia, Emergencia, EstadoEmergencia, OfertaAyuda,
    OfertaItem, Organizacion, RegistroRecursos,
)
from ..repositories import EmergenciaRepository
from .evaluacion_cloud_service import EvaluacionCloudService

ESTADOS_CONFIRMADOS = (EstadoEmergencia.EN_PROCESO, EstadoEmergencia.RESUELTA)


def utc_naive(fecha: Optional[datetime]) -> Optional[datetime]:
    """Fecha en UTC sin zona; las fechas sin zona se asumen ya en UTC."""
    if fecha is None or fecha.tzinfo is None:
        return fecha
    return fecha.astimezone(timezone.utc).replace(tzinfo=None)


def horas_entre(inicio: datetime, fin: datetime) -> float:
    return (utc_naive(fin) - utc_naive(inicio)).total_seconds() / 3600


def promedio(valores: list[float]) -> Optional[float]:
    return round(sum(valores) / len(valores), 2) if valores else None


@dataclass
class DatosTablero:
    emergencias: list[Emergencia]
    ofertas: list[OfertaAyuda]
    confirmacion_por_oferta: dict[int, datetime] = field(default_factory=dict)
    cierres: dict[int, datetime] = field(default_factory=dict)
    # Por emergencia: {(oferta_id, lote_id): cantidad_verificada}; ausente = sin ronda local.
    verificados: dict[int, dict[tuple[int, int], int]] = field(default_factory=dict)
    # Por emergencia: {tipo_recurso_id: cantidad bloqueada}.
    reservados: dict[int, dict[int, int]] = field(default_factory=dict)
    nombres_organizacion: dict[int, str] = field(default_factory=dict)


class TableroService:
    def __init__(self) -> None:
        self._repository = EmergenciaRepository()

    # ---------- carga ----------

    def _emergencias_filtradas(
        self, db: Session, desde: Optional[datetime], hasta: Optional[datetime],
        nivel_gravedad: Optional[str],
    ) -> list[Emergencia]:
        desde, hasta = utc_naive(desde), utc_naive(hasta)
        emergencias = []
        for emergencia in self._repository.listar(db):
            registro = utc_naive(emergencia.fecha_hora_registro)
            if desde is not None and registro < desde:
                continue
            if hasta is not None and registro > hasta:
                continue
            if nivel_gravedad is not None and emergencia.nivel_gravedad != nivel_gravedad:
                continue
            emergencias.append(emergencia)
        return sorted(emergencias, key=lambda e: e.id)

    @staticmethod
    def _verificados_locales(db: Session, emergencia: Emergencia) -> Optional[dict[tuple[int, int], int]]:
        """Ronda vigente guardada localmente; sin ronda local no se consulta Bonita."""
        if not emergencia.bonita_case_id:
            return None
        try:
            evaluacion = EvaluacionCloudService.obtener(db, emergencia.id, emergencia.bonita_case_id)
        except HTTPException:
            return None
        if not isinstance(evaluacion, dict) or not isinstance(evaluacion.get("resultados"), list):
            return None
        cantidades = {}
        for fila in evaluacion["resultados"]:
            if not isinstance(fila, dict):
                continue
            oferta_id, lote_id, cantidad = (fila.get("oferta_id"), fila.get("lote_id"),
                                            fila.get("cantidad_verificada"))
            if all(type(v) is int for v in (oferta_id, lote_id, cantidad)) and cantidad >= 0:
                cantidades[(oferta_id, lote_id)] = cantidad
        return cantidades

    @staticmethod
    def _reservados(registro: RegistroRecursos) -> dict[int, int]:
        try:
            recibo = json.loads(registro.respuesta_json or "{}")
            bloqueados = recibo.get("bloqueados", [])
        except (ValueError, AttributeError):
            return {}
        cantidades: dict[int, int] = defaultdict(int)
        for fila in bloqueados if isinstance(bloqueados, list) else []:
            if isinstance(fila, dict) and type(fila.get("item_id")) is int and type(fila.get("cantidad")) is int:
                cantidades[fila["item_id"]] += fila["cantidad"]
        return dict(cantidades)

    def cargar(
        self, db: Session, desde: Optional[datetime], hasta: Optional[datetime],
        nivel_gravedad: Optional[str],
    ) -> DatosTablero:
        emergencias = self._emergencias_filtradas(db, desde, hasta, nivel_gravedad)
        ids = [e.id for e in emergencias]
        if not ids:
            return DatosTablero(emergencias=[], ofertas=[])
        ofertas = (
            db.query(OfertaAyuda)
            .filter(OfertaAyuda.emergencia_id.in_(ids))
            .options(
                selectinload(OfertaAyuda.organizacion),
                selectinload(OfertaAyuda.items).selectinload(OfertaItem.aportes),
                selectinload(OfertaAyuda.items).selectinload(OfertaItem.lote_necesidad),
            )
            .order_by(OfertaAyuda.id)
            .all()
        )
        datos = DatosTablero(emergencias=emergencias, ofertas=ofertas)
        ids_ofertas = [o.id for o in ofertas]
        avisos = ({a.oferta_id: a.creada_en for a in db.query(AvisoAdjudicacion)
                   .filter(AvisoAdjudicacion.oferta_id.in_(ids_ofertas))} if ids_ofertas else {})
        for oferta in ofertas:
            fecha = avisos.get(oferta.id) or oferta.adjudicada_en
            if fecha is not None:
                datos.confirmacion_por_oferta[oferta.id] = utc_naive(fecha)
        datos.cierres = {
            c.emergencia_id: utc_naive(c.resuelta_en)
            for c in db.query(CierreEmergencia).filter(CierreEmergencia.emergencia_id.in_(ids))
        }
        for emergencia in emergencias:
            verificados = self._verificados_locales(db, emergencia)
            if verificados is not None:
                datos.verificados[emergencia.id] = verificados
        for registro in (db.query(RegistroRecursos)
                         .filter(RegistroRecursos.emergencia_id.in_(ids),
                                 RegistroRecursos.estado == "CONFIRMADO")):
            datos.reservados[registro.emergencia_id] = self._reservados(registro)
        ids_organizaciones = {o.organizacion_id for o in ofertas} | {
            a.organizacion_id for o in ofertas for i in o.items for a in i.aportes
        }
        datos.nombres_organizacion = {
            org.id: org.nombre
            for org in db.query(Organizacion).filter(Organizacion.id.in_(ids_organizaciones))
        } if ids_organizaciones else {}
        return datos

    @staticmethod
    async def consultar_bonita(casos: set[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Devuelve (métricas, error). Bonita caído no interrumpe el tablero."""
        if not casos:
            return {"casos": {}, "tiempos_por_etapa": bonita_client._tiempos_por_etapa([], [])[0],
                    "casos_camino_alternativo": 0}, None
        try:
            return await bonita_client.obtener_metricas_casos(casos), None
        except (BonitaClientError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            return None, str(exc) or exc.__class__.__name__

    # ---------- armado ----------

    async def obtener_tablero(
        self, db: Session, desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
        nivel_gravedad: Optional[str] = None,
    ) -> TableroRespuesta:
        datos = await run_in_threadpool(self.cargar, db, desde, hasta, nivel_gravedad)
        casos = {e.bonita_case_id for e in datos.emergencias if e.bonita_case_id}
        bonita, error = await self.consultar_bonita(casos)
        return await run_in_threadpool(self.armar, datos, bonita, error, desde, hasta, nivel_gravedad)

    def armar(
        self, datos: DatosTablero, bonita: Optional[dict[str, Any]], error_bonita: Optional[str],
        desde: Optional[datetime], hasta: Optional[datetime], nivel_gravedad: Optional[str],
    ) -> TableroRespuesta:
        ahora = utc_naive(datetime.now(timezone.utc))
        emergencias = datos.emergencias
        por_id = {e.id: e for e in emergencias}
        confirmadas = [
            o for o in datos.ofertas
            if o.adjudicada_en is not None and por_id[o.emergencia_id].estado in ESTADOS_CONFIRMADOS
        ]
        casos_bonita = (bonita or {}).get("casos", {})

        # Fecha de resolución: cierre local o, si falta, end_date del caso completed en Bonita.
        resueltas = [e for e in emergencias if e.estado == EstadoEmergencia.RESUELTA]
        resolucion: dict[int, float] = {}
        fuente_local = fuente_bonita = 0
        sin_fecha: list[int] = []
        fecha_cierre: dict[int, datetime] = {}
        for emergencia in resueltas:
            fin = datos.cierres.get(emergencia.id)
            if fin is not None:
                fuente_local += 1
            else:
                caso = casos_bonita.get(emergencia.bonita_case_id or "", {})
                if caso.get("estado") == "completed" and caso.get("fin") is not None:
                    fin = caso["fin"]
                    fuente_bonita += 1
            if fin is None:
                sin_fecha.append(emergencia.id)
                continue
            fecha_cierre[emergencia.id] = fin
            resolucion[emergencia.id] = horas_entre(emergencia.fecha_hora_registro, fin)

        def verificado_de(oferta: OfertaAyuda, item: OfertaItem) -> Optional[int]:
            return datos.verificados.get(oferta.emergencia_id, {}).get((oferta.id, item.lote_necesidad_id))

        def confirmado_de(oferta: OfertaAyuda, item: OfertaItem) -> int:
            verificado = verificado_de(oferta, item)
            return verificado if verificado is not None else item.cantidad_ofrecida

        resumen = self._resumen(emergencias, ahora, resolucion, fuente_local, fuente_bonita,
                                sin_fecha, fecha_cierre)
        recursos = self._recursos(datos, confirmadas, verificado_de, confirmado_de)
        proyectos = self._proyectos(datos, confirmadas, resueltas, resolucion, confirmado_de)
        return TableroRespuesta(
            generado_en=ahora,
            filtros=FiltrosAplicados(desde=utc_naive(desde), hasta=utc_naive(hasta),
                                     nivel_gravedad=nivel_gravedad),
            resumen=resumen,
            recursos=recursos,
            proyectos=proyectos,
            bonita=self._bonita(emergencias, bonita, error_bonita),
        )

    @staticmethod
    def _resumen(emergencias, ahora, resolucion, fuente_local, fuente_bonita, sin_fecha, fecha_cierre):
        ids = [e.id for e in emergencias]
        abiertas = [e for e in emergencias if e.estado != EstadoEmergencia.RESUELTA]
        resueltas = [e for e in emergencias if e.estado == EstadoEmergencia.RESUELTA]
        conteo: dict[tuple[str, str], int] = defaultdict(int)
        for e in emergencias:
            conteo[(e.estado or "", e.nivel_gravedad)] += 1
        con_prioridad = [e for e in abiertas if e.prioridad is not None]
        evolucion: dict[str, dict[str, int]] = defaultdict(lambda: {"aperturas": 0, "cierres": 0})
        for e in emergencias:
            evolucion[utc_naive(e.fecha_hora_registro).date().isoformat()]["aperturas"] += 1
        for emergencia_id, fin in fecha_cierre.items():
            evolucion[fin.date().isoformat()]["cierres"] += 1
        base = {"alcance": "filtrado"}
        return ResumenTablero(
            total=IndicadorConteo(valor=len(emergencias), descripcion="Emergencias registradas en el período y gravedad filtrados.",
                                  fuente="local", emergencias_incluidas=ids, **base),
            abiertas=IndicadorConteo(valor=len(abiertas), descripcion="Emergencias que todavía no se marcaron resueltas.",
                                     fuente="local", emergencias_incluidas=[e.id for e in abiertas], **base),
            resueltas=IndicadorConteo(valor=len(resueltas), descripcion="Emergencias marcadas resueltas.",
                                      fuente="local", emergencias_incluidas=[e.id for e in resueltas], **base),
            por_estado_y_gravedad=IndicadorEstadoGravedad(
                filas=[FilaEstadoGravedad(estado=estado, nivel_gravedad=gravedad, cantidad=cantidad)
                       for (estado, gravedad), cantidad in sorted(conteo.items())],
                descripcion="Cantidad de emergencias por estado y nivel de gravedad.",
                fuente="local", emergencias_incluidas=ids, **base),
            prioridad_promedio_abiertas=IndicadorPromedioValor(
                valor=promedio([e.prioridad for e in con_prioridad]), n=len(con_prioridad),
                descripcion="Prioridad promedio (1 a 10) de las emergencias abiertas con prioridad calculada.",
                fuente="local", emergencias_incluidas=[e.id for e in con_prioridad], **base),
            antiguedad_abiertas_horas=IndicadorPromedioHoras(
                promedio=promedio([horas_entre(e.fecha_hora_registro, ahora) for e in abiertas]), n=len(abiertas),
                descripcion="Horas promedio desde el registro hasta ahora de las emergencias abiertas.",
                fuente="local", emergencias_incluidas=[e.id for e in abiertas], **base),
            resolucion_horas=IndicadorResolucion(
                promedio=promedio(list(resolucion.values())), n=len(resolucion),
                fuente_fecha=FuenteFechaCierre(local=fuente_local, bonita=fuente_bonita),
                sin_fecha_cierre=sin_fecha,
                descripcion="Horas promedio desde el registro hasta la resolución de las emergencias resueltas con fecha de cierre conocida.",
                fuente="local+bonita", emergencias_incluidas=sorted(resolucion), **base),
            evolucion=IndicadorEvolucion(
                filas=[FilaEvolucion(fecha=fecha, **valores) for fecha, valores in sorted(evolucion.items())],
                descripcion="Aperturas por fecha de registro y cierres por fecha de resolución, por día (UTC).",
                fuente="local+bonita", emergencias_incluidas=ids, **base),
        )

    @staticmethod
    def _recursos(datos: DatosTablero, confirmadas, verificado_de, confirmado_de) -> RecursosTablero:
        ids_confirmadas = {o.id for o in confirmadas}
        filas_lote: list[RecursoPorLote] = []
        items_por_lote: dict[int, list[tuple[OfertaAyuda, OfertaItem]]] = defaultdict(list)
        for oferta in datos.ofertas:
            for item in oferta.items:
                items_por_lote[item.lote_necesidad_id].append((oferta, item))
        for emergencia in datos.emergencias:
            for lote in sorted(emergencia.lotes, key=lambda l: l.id):
                pares = items_por_lote.get(lote.id, [])
                verificado = None
                if emergencia.id in datos.verificados:
                    verificado = sum(datos.verificados[emergencia.id].get((o.id, lote.id), 0) for o, _ in pares)
                cubierto = sum(confirmado_de(o, i) for o, i in pares if o.id in ids_confirmadas)
                filas_lote.append(RecursoPorLote(
                    lote_id=lote.id, emergencia_id=emergencia.id, tipo_recurso=lote.tipo,
                    tipo_recurso_id=lote.tipo_recurso_id, unidad=lote.unidad, pedido=lote.cantidad,
                    ofertado=sum(i.cantidad_ofrecida for _, i in pares), verificado=verificado,
                    cubierto_confirmado=cubierto,
                    porcentaje_cobertura=round(cubierto * 100 / lote.cantidad, 2) if lote.cantidad else None,
                ))

        totales: dict[tuple, dict[str, int]] = defaultdict(
            lambda: {"ofertado": 0, "verificado": 0, "reservado": 0, "entregado": 0})

        def mes(fecha: Optional[datetime]) -> Optional[str]:
            return utc_naive(fecha).strftime("%Y-%m") if fecha is not None else None

        for oferta in datos.ofertas:
            for item in oferta.items:
                lote = item.lote_necesidad
                clave_oferta = (mes(oferta.fecha_hora_oferta), lote.tipo, lote.tipo_recurso_id, lote.unidad)
                totales[clave_oferta]["ofertado"] += item.cantidad_ofrecida
                verificado = verificado_de(oferta, item)
                if verificado is not None:
                    totales[clave_oferta]["verificado"] += verificado
                if oferta.id in ids_confirmadas and item.finalizado_en is not None:
                    clave = (mes(datos.confirmacion_por_oferta.get(oferta.id)), lote.tipo,
                             lote.tipo_recurso_id, lote.unidad)
                    totales[clave]["entregado"] += confirmado_de(oferta, item)
        por_id = {e.id: e for e in datos.emergencias}
        for emergencia_id, cantidades in datos.reservados.items():
            fechas = [datos.confirmacion_por_oferta[o.id] for o in confirmadas
                      if o.emergencia_id == emergencia_id and o.id in datos.confirmacion_por_oferta]
            mes_reserva = mes(min(fechas)) if fechas else None
            lotes = sorted(por_id[emergencia_id].lotes, key=lambda l: l.id)
            for tipo_id, cantidad in sorted(cantidades.items()):
                lote = next((l for l in lotes if l.tipo_recurso_id == tipo_id), None)
                clave = (mes_reserva, lote.tipo if lote else f"Recurso {tipo_id}", tipo_id,
                         lote.unidad if lote else None)
                totales[clave]["reservado"] += cantidad
        filas_totales = [
            TotalRecursoMes(mes=m, tipo_recurso=t, tipo_recurso_id=tid, unidad=u, **valores)
            for (m, t, tid, u), valores in sorted(
                totales.items(), key=lambda kv: (kv[0][0] or "", kv[0][1], kv[0][2] or 0, kv[0][3] or ""))
        ]
        hay_entrega = any(f.entregado > 0 for f in filas_totales)
        ids = [e.id for e in datos.emergencias]
        return RecursosTablero(
            por_lote=IndicadorRecursosPorLote(
                filas=filas_lote,
                descripcion="Por lote: pedido, ofertado, verificado por el Sistema Nacional y cubierto por ofertas con selección confirmada.",
                fuente="local+cloud", alcance="filtrado",
                emergencias_incluidas=sorted({f.emergencia_id for f in filas_lote})),
            totales=IndicadorTotalesRecursos(
                filas=filas_totales,
                descripcion="Totales por mes, tipo y unidad: ofertado y verificado (mes de la oferta); reservado y entregado (mes de confirmación).",
                fuente="local+cloud", alcance="filtrado", emergencias_incluidas=ids),
            etiqueta_recursos="Recursos entregados" if hay_entrega else "Recursos reservados",
        )

    def _proyectos(self, datos: DatosTablero, confirmadas, resueltas, resolucion, confirmado_de) -> ProyectosTablero:
        por_emergencia: dict[int, list[OfertaAyuda]] = defaultdict(list)
        for oferta in confirmadas:
            por_emergencia[oferta.emergencia_id].append(oferta)
        filas = []
        for emergencia in datos.emergencias:
            ofertas = por_emergencia.get(emergencia.id)
            if not ofertas:
                continue
            items = [(o, i) for o in ofertas for i in o.items]
            cantidades: dict[tuple[str, Optional[str]], dict[str, int]] = defaultdict(
                lambda: {"confirmado": 0, "entregado": 0})
            for oferta, item in items:
                clave = (item.lote_necesidad.tipo, item.lote_necesidad.unidad)
                cantidad = confirmado_de(oferta, item)
                cantidades[clave]["confirmado"] += cantidad
                if item.finalizado_en is not None:
                    cantidades[clave]["entregado"] += cantidad
            filas.append(ProyectoTablero(
                emergencia_id=emergencia.id, zona_afectada=emergencia.zona_afectada,
                estado=emergencia.estado, bonita_case_id=emergencia.bonita_case_id,
                items_totales=len(items),
                items_finalizados=sum(1 for _, i in items if i.finalizado_en is not None),
                cantidades=[CantidadPorUnidad(tipo_recurso=t, unidad=u, **v)
                            for (t, u), v in sorted(cantidades.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))],
                resuelta=emergencia.estado == EstadoEmergencia.RESUELTA,
                resolucion_horas=round(resolucion[emergencia.id], 2) if emergencia.id in resolucion else None,
            ))

        con_consorcio = [e.id for e in resueltas
                         if any(o.es_conjunta for o in por_emergencia.get(e.id, []))]
        ranking: dict[tuple[int, str, Optional[str]], float] = defaultdict(float)
        for oferta in confirmadas:
            for item in oferta.items:
                cantidad = confirmado_de(oferta, item)
                clave_recurso = (item.lote_necesidad.tipo, item.lote_necesidad.unidad)
                total_aportes = sum(a.cantidad for a in item.aportes)
                if oferta.es_conjunta and total_aportes > 0:
                    for aporte in item.aportes:
                        ranking[(aporte.organizacion_id, *clave_recurso)] += cantidad * aporte.cantidad / total_aportes
                else:
                    ranking[(oferta.organizacion_id, *clave_recurso)] += cantidad
        filas_ranking = [
            FilaRankingONG(organizacion_id=org, organizacion_nombre=datos.nombres_organizacion.get(org, f"Organización {org}"),
                           tipo_recurso=tipo, unidad=unidad, cantidad_confirmada=round(cantidad, 2))
            for (org, tipo, unidad), cantidad in sorted(
                ranking.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1], kv[0][2] or ""))
        ]
        ids_confirmadas = sorted({o.emergencia_id for o in confirmadas})
        return ProyectosTablero(
            proyectos=IndicadorProyectos(
                filas=filas,
                descripcion="Emergencias con al menos una oferta con selección confirmada: avance de ítems y cantidades.",
                fuente="local+cloud+bonita", alcance="filtrado", emergencias_incluidas=ids_confirmadas),
            consorcios=IndicadorConsorcios(
                emergencias_resueltas=len(resueltas), resueltas_con_consorcio=len(con_consorcio),
                porcentaje=round(len(con_consorcio) * 100 / len(resueltas), 2) if resueltas else None,
                descripcion="Porcentaje de emergencias resueltas con al menos una oferta conjunta confirmada.",
                fuente="local", alcance="filtrado", emergencias_incluidas=sorted(e.id for e in resueltas)),
            ranking_ongs=IndicadorRankingONG(
                filas=filas_ranking,
                descripcion="Cantidad confirmada por ONG, tipo y unidad; en consorcios se reparte según los aportes declarados.",
                fuente="local+cloud", alcance="filtrado", emergencias_incluidas=ids_confirmadas),
        )

    @staticmethod
    def _bonita(emergencias, bonita: Optional[dict[str, Any]], error: Optional[str]) -> BonitaTablero:
        con_caso = [e for e in emergencias if e.bonita_case_id]
        meta = {
            "descripcion": "Estado de los casos de Bonita de las emergencias filtradas, tiempos por etapa y verificación caso por caso.",
            "fuente": "bonita", "alcance": "filtrado",
            "emergencias_incluidas": [e.id for e in con_caso],
        }
        if bonita is None:
            return BonitaTablero(disponible=False, error=error, casos_activos=0, casos_finalizados=0,
                                 casos_cancelados=0, tiempos_por_etapa=[], casos_camino_alternativo=0,
                                 verificacion=[], **meta)
        casos = bonita.get("casos", {})
        estados = [casos.get(e.bonita_case_id, {}).get("estado", "no_encontrado") for e in con_caso]
        verificacion = []
        for emergencia, estado in zip(con_caso, estados):
            caso = casos.get(emergencia.bonita_case_id, {})
            horas = None
            if estado == "completed" and caso.get("inicio") and caso.get("fin"):
                horas = round(horas_entre(caso["inicio"], caso["fin"]), 2)
            verificacion.append(VerificacionCaso(
                emergencia_id=emergencia.id, bonita_case_id=emergencia.bonita_case_id,
                estado_local=emergencia.estado, estado_bonita=estado, resolucion_horas=horas))
        return BonitaTablero(
            disponible=True, error=None,
            casos_activos=estados.count("activo"),
            casos_finalizados=estados.count("completed"),
            casos_cancelados=estados.count("cancelado"),
            tiempos_por_etapa=[
                TiempoEtapa(etapa=t["etapa"], n=t["cantidad"],
                            promedio_horas=round(t["promedio_horas"], 2) if t["cantidad"] else None)
                for t in bonita.get("tiempos_por_etapa", [])
            ],
            casos_camino_alternativo=bonita.get("casos_camino_alternativo", 0),
            verificacion=verificacion, **meta,
        )
