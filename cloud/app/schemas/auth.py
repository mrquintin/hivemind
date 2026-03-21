from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class ClientConnectRequest(BaseModel):
    license_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
