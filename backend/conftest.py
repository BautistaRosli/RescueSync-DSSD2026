"""Deja `backend/` en el sys.path para que los tests importen `app.*`.

Los tests no dependen de una base de datos real: el engine se crea pero no se
conecta hasta que se usa una sesion, y los repositorios van mockeados.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))