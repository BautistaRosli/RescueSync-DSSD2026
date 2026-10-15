from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import salud_api

app = FastAPI(
    title="API Sistema Nacional",
    description="Microservicio del Sistema Nacional de RescueSync.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salud_api.router)