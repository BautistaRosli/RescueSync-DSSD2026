from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  # registra los modelos en Base.metadata
from .api.routes import (
    auth,
    bonita,
    emergencias,
    lotes,
    municipios,
    ofertas,
    organizaciones,
    roles,
)
from .db import Base, SessionLocal, engine
from .services import rol_service

Base.metadata.create_all(bind=engine)


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
app.include_router(municipios.router, prefix=API_PREFIX)
app.include_router(organizaciones.router, prefix=API_PREFIX)
app.include_router(roles.router, prefix=API_PREFIX)
app.include_router(emergencias.router, prefix=API_PREFIX)
app.include_router(lotes.router, prefix=API_PREFIX)
app.include_router(ofertas.router, prefix=API_PREFIX)
app.include_router(bonita.router, prefix=API_PREFIX)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "FastAPI corriendo correctamente"}