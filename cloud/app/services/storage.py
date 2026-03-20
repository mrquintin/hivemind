from __future__ import annotations

import json
import re
import uuid
from typing import Tuple

import boto3

from app.config import settings
from app.runtime_paths import uploads_root


def _safe_filename(filename: str) -> str:
    """Sanitize filename for local paths and S3 keys to prevent path traversal and invalid chars."""
    base = (filename or "file").replace("\\", "_").replace("/", "_").strip()
    base = re.sub(r"[^\w.\-]", "_", base)
    return base or "file"


def _s3_client():
    if not settings.S3_BUCKET:
        return None

    if settings.S3_CREDENTIALS:
        creds = json.loads(settings.S3_CREDENTIALS)
        # Support both access_key/secret_key and aws_access_key_id/aws_secret_access_key
        access = creds.get("access_key") or creds.get("aws_access_key_id")
        secret = creds.get("secret_key") or creds.get("aws_secret_access_key")
        session = boto3.session.Session(
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=creds.get("region") or settings.AWS_REGION,
        )
    else:
        # On AWS, boto3 can use the instance/task IAM role automatically.
        session = boto3.session.Session(region_name=settings.AWS_REGION)

    return session.client("s3")


def store_file(
    filename: str,
    data: bytes,
    document_type: str = "framework",
) -> Tuple[str, str]:
    """Store a file, organizing into subfolders by document type.

    Folder layout:
        uploads/
            knowledge/
                frameworks/      ← TXT files describing frameworks/algorithms
            simulations/         ← .py programs and their companion .txt descriptions
            practicality/        ← TXT files for practicality network constraints/scoring
    """
    subfolder = {
        "framework": "knowledge/frameworks",
        "simulation_program": "simulations",
        "simulation_description": "simulations",
        "practicality": "practicality",
    }.get(document_type, "knowledge/frameworks")

    safe_name = _safe_filename(filename)
    client = _s3_client()
    if client and settings.S3_BUCKET:
        # Use unique prefix to avoid overwrites; S3 keys are safe
        unique = uuid.uuid4().hex[:8]
        key = f"{subfolder}/{unique}_{safe_name}"
        client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data)
        return f"s3://{settings.S3_BUCKET}/{key}", key

    uploads_dir = uploads_root() / subfolder
    uploads_dir.mkdir(parents=True, exist_ok=True)
    filepath = uploads_dir / safe_name
    filepath.write_bytes(data)
    return f"local://{filepath}", str(filepath)
