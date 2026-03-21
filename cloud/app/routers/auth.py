from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_any_authenticated, get_db
from app.models.client import Client
from app.routers.settings import get_active_api_key
from app.schemas.auth import ClientConnectRequest, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_token(subject: str, extra: dict | None = None) -> str:
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRES_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _get_cleared_usernames() -> set[str]:
    if not settings.CLEARED_USERNAMES:
        return set()
    return {
        name.strip().lower()
        for name in settings.CLEARED_USERNAMES.split(",")
        if name.strip()
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    cleared_usernames = _get_cleared_usernames()
    if cleared_usernames and username.lower() not in cleared_usernames:
        raise HTTPException(status_code=403, detail="Username is not cleared")

    # Set the API key from env/file (no hardcoded fallback; use ANTHROPIC_API_KEY or .api_key on AWS)
    api_key = get_active_api_key()
    if api_key:
        settings.ANTHROPIC_API_KEY = api_key
    
    token = _create_token(username, {"role": "operator"})
    return TokenResponse(access_token=token)


@router.post("/client-connect", response_model=TokenResponse)
def client_connect(payload: ClientConnectRequest, db: Session = Depends(get_db)) -> TokenResponse:
    client = db.query(Client).filter(Client.license_key == payload.license_key).first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid license key")
    token = _create_token(client.id, {"role": "client"})
    return TokenResponse(access_token=token)


@router.get("/me")
def get_me(current_user: dict = Depends(get_any_authenticated)):
    """Return the identity of the currently authenticated user."""
    return {
        "username": current_user["sub"],
        "role": current_user["role"],
        "client_id": current_user["sub"],
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    current_user: dict = Depends(get_any_authenticated),
) -> TokenResponse:
    """Re-issue a token with the same sub/role and a fresh expiry."""
    token = _create_token(current_user["sub"], {"role": current_user["role"]})
    return TokenResponse(access_token=token)
