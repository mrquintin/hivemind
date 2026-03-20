from __future__ import annotations

import os
from pathlib import Path


_APP_ROOT = Path(__file__).resolve().parents[1]


def runtime_root() -> Path:
    """Return the writable runtime directory for server state."""
    configured = os.getenv("HIVEMIND_DATA_DIR")
    root = Path(configured).expanduser() if configured else _APP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def logs_dir() -> Path:
    path = runtime_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_root() -> Path:
    configured = os.getenv("HIVEMIND_UPLOADS_DIR")
    if configured:
        path = Path(configured).expanduser()
    elif os.getenv("HIVEMIND_DATA_DIR"):
        path = runtime_root() / "uploads"
    else:
        path = _APP_ROOT / "uploads"

    path.mkdir(parents=True, exist_ok=True)
    return path


def api_key_file() -> Path:
    return runtime_root() / ".api_key"


def settings_file() -> Path:
    return runtime_root() / ".hivemind_settings.json"
