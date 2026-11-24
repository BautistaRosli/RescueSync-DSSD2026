"""Reglas compartidas para nombres de recursos."""

import re


def normalizar_nombre_recurso(valor: str) -> str:
    """Limpia espacios y deja solo la primera letra en mayúscula."""
    limpio = re.sub(r"\s+", " ", valor or "").strip().lower()
    return limpio[:1].upper() + limpio[1:]
