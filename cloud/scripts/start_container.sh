#!/usr/bin/env bash

set -euo pipefail

cd /app/cloud

python - <<'PY'
import os
import sys
import time
import urllib.request

from sqlalchemy import create_engine, text


def wait_for_postgres(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds

    while True:
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[startup] PostgreSQL is ready")
            return
        except Exception as exc:  # pragma: no cover - startup script
            if time.time() >= deadline:
                print(f"[startup] Timed out waiting for PostgreSQL: {exc}", file=sys.stderr)
                raise
            print(f"[startup] Waiting for PostgreSQL: {exc}")
            time.sleep(3)


def wait_for_qdrant(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    # Qdrant exposes /healthz (not /health); see https://qdrant.tech/documentation/guides/monitoring
    health_url = f"{url.rstrip('/')}/healthz"

    while True:
        try:
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                if resp.status == 200:
                    print("[startup] Qdrant is ready")
                    return
                raise RuntimeError(f"unexpected HTTP {resp.status}")
        except Exception as exc:  # pragma: no cover - startup script
            if time.time() >= deadline:
                print(f"[startup] Timed out waiting for Qdrant: {exc}", file=sys.stderr)
                raise
            print(f"[startup] Waiting for Qdrant: {exc}")
            time.sleep(3)


database_url = os.environ.get("DATABASE_URL")
vector_db_url = os.environ.get("VECTOR_DB_URL")

if not database_url:
    raise SystemExit("DATABASE_URL is required")

if not vector_db_url:
    raise SystemExit("VECTOR_DB_URL is required")

wait_for_postgres(database_url)
wait_for_qdrant(vector_db_url)
PY

exec uvicorn app.main:app --host "${SERVER_HOST:-0.0.0.0}" --port "${SERVER_PORT:-8000}"
