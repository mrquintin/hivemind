"""Server settings endpoints — API key management, etc."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_current_user
from app.secrets import encrypt_api_key, decrypt_api_key, read_api_key_file, write_api_key_file
from app.runtime_paths import settings_file

router = APIRouter(prefix="/settings", tags=["settings"])

_SETTINGS_FILE = settings_file()


def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        return json.loads(_SETTINGS_FILE.read_text())
    return {}


def _save_settings(data: dict) -> None:
    _SETTINGS_FILE.write_text(json.dumps(data, indent=2))


class ApiKeyPayload(BaseModel):
    api_key: str


@router.post("/api-key")
def set_api_key(payload: ApiKeyPayload, _user: dict = Depends(get_current_user)):
    """Store the Anthropic API key (encrypted at rest)."""
    key = payload.api_key.strip()
    if not key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="Invalid API key format")

    # Write to .api_key file (primary storage, archives with the software)
    write_api_key_file(key)
    # Also update .hivemind_settings.json for backward compatibility
    encrypted = encrypt_api_key(key)
    data = _load_settings()
    data["encrypted_anthropic_key"] = encrypted
    _save_settings(data)
    return {"status": "saved"}


@router.get("/api-key-status")
def get_api_key_status(_user: dict = Depends(get_current_user)):
    """Check whether an API key is configured (does not reveal the key)."""
    # Check .api_key file first (primary)
    key = read_api_key_file()
    if key:
        return {
            "configured": True,
            "source": "api_key_file",
            "masked": f"sk-...{key[-4:]}" if len(key) > 4 else "sk-...",
        }

    # Check runtime settings file
    data = _load_settings()
    if data.get("encrypted_anthropic_key"):
        try:
            key = decrypt_api_key(data["encrypted_anthropic_key"])
            return {
                "configured": True,
                "source": "server_settings",
                "masked": f"sk-...{key[-4:]}",
            }
        except Exception:
            pass

    # Fall back to environment variable / .env (used on AWS)
    from app.config import settings

    if settings.ANTHROPIC_API_KEY:
        k = settings.ANTHROPIC_API_KEY
        return {
            "configured": True,
            "source": "environment",
            "masked": f"sk-...{k[-4:]}" if len(k) > 4 else "sk-...",
        }

    return {"configured": False, "source": None, "masked": None}


def get_active_api_key() -> str | None:
    """Resolve the active API key from all sources.

    Priority: .api_key file > .hivemind_settings.json > env var.
    No hardcoded fallback; use ANTHROPIC_API_KEY on AWS.
    """
    # 1. .api_key file (encrypted, travels with archives)
    key = read_api_key_file()
    if key:
        return key

    # 2. Runtime settings file (.hivemind_settings.json)
    data = _load_settings()
    if data.get("encrypted_anthropic_key"):
        try:
            return decrypt_api_key(data["encrypted_anthropic_key"])
        except Exception:
            pass

    # 3. Environment / .env (primary on AWS)
    from app.config import settings

    if settings.ANTHROPIC_API_KEY:
        return settings.ANTHROPIC_API_KEY

    return None
