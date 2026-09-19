import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BONITA_URL = os.getenv("BONITA_URL", "http://host.docker.internal:8080/bonita")
BONITA_USER = os.getenv("BONITA_USER", "install")
BONITA_PASSWORD = os.getenv("BONITA_PASSWORD", "install")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "FastAPI corriendo correctamente"}

@app.post("/bonita/test-login")
async def test_bonita_connection():
    """Valida conexión y autenticación con el motor Bonita BPM."""
    login_url = f"{BONITA_URL}/loginservice"
    payload = {
        "username": BONITA_USER,
        "password": BONITA_PASSWORD,
        "redirect": "false"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                login_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if res.status_code != 204 and res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail="Fallo de autenticación en Bonita")
            
            cookies = res.cookies
            bonita_token = cookies.get("X-Bonita-API-Token")
            
            return {
                "status": "connected",
                "session_active": True,
                "has_csrf_token": bonita_token is not None
            }
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"No se pudo conectar a Bonita: {exc}")