from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# importa los modelos de todos los dominios para registrarlos en Base.metadata
from . import models as modelos
from .api.routes import (
    auth_api,
    bonita_api,
    emergencias_api,
    inventario_api,
    lotes_api,
    ofertas_api,
    organizaciones_api,
    roles_api,
)
from .database import Base, SessionLocal, engine
from .services.usuarios_service import AuthService, RolService

with engine.begin() as conexion:
    if conexion.dialect.name == "postgresql":
        # Serializa el check/create de tablas cuando arrancan varios procesos.
        conexion.execute(text("SELECT pg_advisory_xact_lock(2026, 1)"))
    Base.metadata.create_all(bind=conexion)

rol_service = RolService()
auth_service = AuthService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        rol_service.sembrar_roles(db)
        auth_service.sembrar_usuarios_iniciales(db)
    finally:
        db.close()
    yield


app = FastAPI(title="RescueSync API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth_api.router, prefix=API_PREFIX)
app.include_router(organizaciones_api.router, prefix=API_PREFIX)
app.include_router(roles_api.router, prefix=API_PREFIX)
app.include_router(emergencias_api.router, prefix=API_PREFIX)
app.include_router(lotes_api.router, prefix=API_PREFIX)
app.include_router(inventario_api.router, prefix=API_PREFIX)
app.include_router(ofertas_api.router, prefix=API_PREFIX)
app.include_router(bonita_api.router, prefix=API_PREFIX)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "FastAPI corriendo correctamente"}
