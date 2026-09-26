from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# importa los modelos de todos los dominios para registrarlos en Base.metadata
from .domains.emergencias import models as modelos_emergencias
from .domains.lotes import models as modelos_lotes
from .domains.ofertas import models as modelos_ofertas
from .domains.usuarios import models as modelos_usuarios
from .api.routes import (
    auth,
    bonita,
    emergencias,
    lotes,
    ofertas,
    organizaciones,
    roles,
)
from .database import Base, SessionLocal, engine
from .domains.usuarios.service import RolService

Base.metadata.create_all(bind=engine)

rol_service = RolService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        rol_service.sembrar_roles(db)
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
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(organizaciones.router, prefix=API_PREFIX)
app.include_router(roles.router, prefix=API_PREFIX)
app.include_router(emergencias.router, prefix=API_PREFIX)
app.include_router(lotes.router, prefix=API_PREFIX)
app.include_router(ofertas.router, prefix=API_PREFIX)
app.include_router(bonita.router, prefix=API_PREFIX)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "FastAPI corriendo correctamente"}
