from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# importa los modelos de todos los dominios para registrarlos en Base.metadata
from .domains.emergencias import models as modelos_emergencias
from .domains.lotes import models as modelos_lotes
from .domains.ofertas import models as modelos_ofertas
from .domains.usuarios import models as modelos_usuarios
from .api.routes import (
    bonita,
    emergencias,
    lotes,
    municipios,
    ofertas,
    organizaciones,
)
from .database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="RescueSync API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(municipios.router, prefix=API_PREFIX)
app.include_router(organizaciones.router, prefix=API_PREFIX)
app.include_router(emergencias.router, prefix=API_PREFIX)
app.include_router(lotes.router, prefix=API_PREFIX)
app.include_router(ofertas.router, prefix=API_PREFIX)
app.include_router(bonita.router, prefix=API_PREFIX)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "FastAPI corriendo correctamente"}
