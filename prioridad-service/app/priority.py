"""Cálculo puro de prioridad de incidentes.

La prioridad depende únicamente de la gravedad declarada y de la zona del
incidente. Nunca depende del cliente que realiza la solicitud: no se usan
identificadores, direcciones IP, cabeceras ni ningún otro dato del emisor.
El módulo no mantiene estado global mutable, no escribe en disco y no accede
a bases de datos.
"""

GRAVEDAD_SCORE = {"baja": 1, "media": 5, "alta": 8, "critica": 10}
ZONA_SCORE = {"norte": 2, "sur": 2, "este": 1, "oeste": 1, "centro": 0, "periferia": 1}


def _zona_score(zona: str) -> int:
    """Devuelve el puntaje de la zona.

    Si la zona no está en el catálogo se usa un valor estable derivado de la
    suma de los códigos de sus caracteres, acotado con módulo 3.
    """
    return ZONA_SCORE.get(zona.strip().lower(), sum(ord(c) for c in zona.lower()) % 3)


def calcular_prioridad(gravedad: str, zona: str) -> int:
    """Calcula la prioridad de un incidente en el rango [1, 10].

    La prioridad depende exclusivamente de la gravedad y de la zona indicadas
    por el solicitante; nunca del cliente ni de datos del emisor.
    """
    raw = GRAVEDAD_SCORE[gravedad.lower()] + _zona_score(zona)
    return max(1, min(10, raw))
