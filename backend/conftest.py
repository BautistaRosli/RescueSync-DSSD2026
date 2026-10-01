"""Deja `backend/` en el sys.path para que los tests importen `app.*`.

Los tests HTTP utilizan SQLite en memoria; los tests de servicios simulan
repositorios. Las pruebas PostgreSQL opcionales usan TEST_DATABASE_URL.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

# La importación de app.main crea tablas; nunca debe usar una base real en tests.
# Las pruebas opcionales PostgreSQL usan únicamente TEST_DATABASE_URL.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "clave-exclusiva-de-tests-sin-validez-fuera-de-esta-suite-2026"
os.environ["APP_ENV"] = "development"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
