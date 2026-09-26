from pydantic import BaseModel

from ...schemas.usuario import UsuarioRead


class AuthResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    usuario: UsuarioRead
