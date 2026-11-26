from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..models import ConfirmacionSeleccion, Emergencia, EstadoEmergencia


class EmergenciaRepository:
    def obtener_confirmacion(self, db: Session, emergencia_id: int) -> ConfirmacionSeleccion | None:
        """Consultar siempre después de bloquear la emergencia correspondiente."""
        return db.get(ConfirmacionSeleccion, emergencia_id, populate_existing=True)

    def preparar_confirmacion(
        self, db: Session, emergencia_id: int, caso_id: int, seleccion_json: str
    ) -> None:
        db.add(ConfirmacionSeleccion(
            emergencia_id=emergencia_id, caso_id=str(caso_id), seleccion_json=seleccion_json
        ))

    def eliminar_confirmacion(self, db: Session, emergencia_id: int) -> None:
        confirmacion = self.obtener_confirmacion(db, emergencia_id)
        if confirmacion is not None:
            db.delete(confirmacion)

    def _consulta_con_lotes(self, db: Session):
        return db.query(Emergencia).options(selectinload(Emergencia.lotes))

    def listar(
        self,
        db: Session,
        publicada: Optional[bool] = None,
    ) -> list[Emergencia]:
        query = self._consulta_con_lotes(db)
        if publicada is not None:
            query = query.filter(Emergencia.publicada == publicada)
        return query.order_by(Emergencia.id.desc()).all()

    def listar_paginado(
        self,
        db: Session,
        publicada: bool,
        pagina: int,
        por_pagina: int,
        estado: Optional[str] = None,
        casos_bonita: set[str] | None = None,
    ) -> list[Emergencia]:
        """Pagina un bucket de emergencias.

        Las no publicadas se ordenan de la mas vieja a la mas nueva y las
        publicadas al reves. El desempate por id mantiene el orden estable
        entre paginas.
        """
        columnas = (
            (Emergencia.fecha_hora_registro.asc(), Emergencia.id.asc())
            if not publicada
            else (Emergencia.fecha_hora_registro.desc(), Emergencia.id.desc())
        )
        query = (
            self._consulta_con_lotes(db)
            .filter(Emergencia.publicada == publicada)
        )
        if estado is not None:
            query = query.filter(Emergencia.estado == estado)
        if casos_bonita is not None:
            query = query.filter(Emergencia.bonita_case_id.in_(casos_bonita))
        return (
            query
            .order_by(*columnas)
            .limit(por_pagina)
            .offset((pagina - 1) * por_pagina)
            .all()
        )

    def contar_por_publicada(
        self,
        db: Session,
        publicada: bool,
        estado: Optional[str] = None,
        casos_bonita: set[str] | None = None,
    ) -> int:
        query = db.query(func.count(Emergencia.id)).filter(
            Emergencia.publicada == publicada
        )
        if estado is not None:
            query = query.filter(Emergencia.estado == estado)
        if casos_bonita is not None:
            query = query.filter(Emergencia.bonita_case_id.in_(casos_bonita))
        return query.scalar() or 0

    def listar_casos_por_estado(self, db: Session, estado: str) -> set[str]:
        """Lee sólo los casos candidatos, sin materializar emergencias ni lotes."""
        return {
            caso_id for (caso_id,) in db.query(Emergencia.bonita_case_id).filter(
                Emergencia.publicada.is_(True), Emergencia.estado == estado,
                Emergencia.bonita_case_id.isnot(None),
            ).distinct()
            if caso_id and caso_id.isdecimal() and int(caso_id) > 0
        }

    def listar_candidatos_cierre(self, db: Session) -> list[tuple[int, str]]:
        """Captura los identificadores municipales y su caso actual."""
        return [
            (emergencia_id, caso_id)
            for emergencia_id, caso_id in db.query(Emergencia.id, Emergencia.bonita_case_id).filter(
                Emergencia.publicada.is_(True),
                Emergencia.estado == EstadoEmergencia.EN_PROCESO,
                Emergencia.bonita_case_id.isnot(None),
            ).order_by(Emergencia.id)
            if caso_id and caso_id.isdecimal() and int(caso_id) > 0
        ]

    def resolver_candidatos_cierre(
        self, db: Session, candidatos: list[tuple[int, str]], casos_completados: set[str],
    ) -> list[int]:
        """Revalida en cada UPDATE para preservar cambios concurrentes."""
        resueltas = []
        try:
            for emergencia_id, caso_id in candidatos:
                if caso_id not in casos_completados:
                    continue
                cantidad = db.query(Emergencia).filter(
                    Emergencia.id == emergencia_id,
                    Emergencia.bonita_case_id == caso_id,
                    Emergencia.publicada.is_(True),
                    Emergencia.estado == EstadoEmergencia.EN_PROCESO,
                ).update({Emergencia.estado: EstadoEmergencia.RESUELTA}, synchronize_session=False)
                if cantidad:
                    resueltas.append(emergencia_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return resueltas

    def obtener_por_id(
        self, db: Session, emergencia_id: int, bloquear: bool = False
    ) -> Optional[Emergencia]:
        consulta = (
            self._consulta_con_lotes(db)
            .filter(Emergencia.id == emergencia_id)
        )
        if bloquear:
            # Recargar también las relaciones después de esperar el bloqueo.
            consulta = consulta.populate_existing().with_for_update()
        return consulta.scalar()

    def crear(self, db: Session, emergencia: Emergencia) -> Emergencia:
        db.add(emergencia)
        db.commit()
        db.refresh(emergencia)
        return emergencia

    def actualizar(self, db: Session, emergencia: Emergencia) -> Emergencia:
        db.commit()
        db.refresh(emergencia)
        return emergencia
