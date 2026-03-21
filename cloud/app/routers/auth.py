from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_any_authenticated, get_db
from app.models.client import Client
from app.models.user import User
from app.schemas.auth import ClientConnectRequest, LoginRequest, TokenResponse
from app.security import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def _create_token(subject: str, extra: dict | None = None) -> str:
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRES_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Login rate limiting (brute-force protection)
# ---------------------------------------------------------------------------

_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_S = 300  # 5 minutes
_login_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _record_failed_attempt(username: str) -> None:
    with _login_lock:
        _failed_attempts[username].append(time.monotonic())


def _check_login_rate_limit(username: str) -> None:
    now = time.monotonic()
    with _login_lock:
        attempts = _failed_attempts.get(username, [])
        recent = [t for t in attempts if now - t < _LOGIN_WINDOW_S]
        _failed_attempts[username] = recent
        if len(recent) >= _LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    username = payload.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    _check_login_rate_limit(username)

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        _record_failed_attempt(username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = _create_token(user.username, {"role": user.role})
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
