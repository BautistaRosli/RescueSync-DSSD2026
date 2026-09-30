from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..models import Emergencia


class EmergenciaRepository:
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
        return (
            self._consulta_con_lotes(db)
            .filter(Emergencia.publicada == publicada)
            .order_by(*columnas)
            .limit(por_pagina)
            .offset((pagina - 1) * por_pagina)
            .all()
        )

    def contar_por_publicada(self, db: Session, publicada: bool) -> int:
        return (
            db.query(func.count(Emergencia.id))
            .filter(Emergencia.publicada == publicada)
            .scalar()
            or 0
        )

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
