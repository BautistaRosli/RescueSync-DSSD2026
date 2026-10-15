from fastapi import APIRouter

router = APIRouter(tags=["salud"])


@router.get("/")
def raiz() -> dict:
    return {
        "status": "ok",
        "message": "API Sistema Nacional corriendo correctamente",
    }


@router.get("/health")
def estado_servicio() -> dict:
    return {
        "estado": "ok",
        "servicio": "api-sistema-nacional",
        "version": "1.0.0",
    }