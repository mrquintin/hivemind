"""
Secure storage for sensitive API keys.
Keys are encrypted using Fernet symmetric encryption.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet

from app.runtime_paths import api_key_file

# Legacy fallback key material kept for backward compatibility with already
# sealed .api_key files created before per-deployment secrets were supported.
_LEGACY_KEY_MATERIAL = b"hivemind_secure_key_storage_v1"


def _cipher_from_seed(seed: bytes) -> Fernet:
    """Create a Fernet cipher from arbitrary seed bytes."""
    key_material = hashlib.sha256(seed).digest()
    fernet_key = base64.urlsafe_b64encode(key_material)
    return Fernet(fernet_key)


def _active_seed() -> bytes:
    """Resolve encryption seed from environment with safe fallback."""
    # Prefer a dedicated secret. Fall back to JWT secret for convenience.
    configured = (os.getenv("HIVEMIND_ENCRYPTION_SECRET") or os.getenv("JWT_SECRET") or "").strip()
    if configured and configured != "change-me":
        return configured.encode("utf-8")
    return _LEGACY_KEY_MATERIAL


def _cipher_candidates() -> list[Fernet]:
    """Return decryption candidates (active first, then legacy when needed)."""
    active_seed = _active_seed()
    candidates = [_cipher_from_seed(active_seed)]
    if active_seed != _LEGACY_KEY_MATERIAL:
        candidates.append(_cipher_from_seed(_LEGACY_KEY_MATERIAL))
    return candidates


def decrypt_api_key(encrypted_value: str) -> str:
    """Decrypt an API key that was encrypted with encrypt_api_key()."""
    for cipher in _cipher_candidates():
        try:
            decrypted = cipher.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except Exception:
            continue
    raise ValueError("Unable to decrypt API key with configured secrets")


def encrypt_api_key(plain_value: str) -> str:
    """Encrypt an API key for storage. Used once to generate the encrypted value."""
    cipher = _cipher_candidates()[0]
    encrypted = cipher.encrypt(plain_value.encode())
    return encrypted.decode()


# =============================================================================
# .api_key FILE — drop-in encrypted key storage
# =============================================================================
# The .api_key file lives at the cloud/ root so it archives with the software.
# Workflow:
#   1. Paste your plaintext sk-... key into cloud/.api_key
#   2. On server startup, seal_api_key_file() encrypts it in place
#   3. The file now contains only the encrypted blob
#   4. Runtime reads and decrypts transparently
# =============================================================================

_API_KEY_FILE = api_key_file()


def seal_api_key_file() -> bool:
    """If .api_key contains a plaintext key, encrypt it in place. Returns True if sealed."""
    if not _API_KEY_FILE.exists():
        return False
    raw = _API_KEY_FILE.read_text().strip()
    # Extract a plaintext key (sk-...) from the file contents
    plaintext = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("sk-") and len(line) > 10:
            plaintext = line
            break
    if not plaintext:
        return False  # No plaintext key found (already encrypted or empty)
    encrypted = encrypt_api_key(plaintext)
    _API_KEY_FILE.write_text(encrypted + "\n")
    return True


def read_api_key_file() -> str | None:
    """Read and decrypt the API key from .api_key. Returns None if missing or invalid."""
    if not _API_KEY_FILE.exists():
        return None
    raw = _API_KEY_FILE.read_text().strip()
    if not raw:
        return None
    # If it's still plaintext (user just dropped it in), use it directly
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("sk-") and len(line) > 10:
            return line
    # Otherwise try to decrypt the encrypted blob
    try:
        return decrypt_api_key(raw)
    except Exception:
        return None


def write_api_key_file(plain_key: str) -> None:
    """Encrypt and write a key to the .api_key file."""
    encrypted = encrypt_api_key(plain_key)
    _API_KEY_FILE.write_text(encrypted + "\n")


# =============================================================================
# UTILITY: Run this file directly to encrypt a new key
# =============================================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        key_to_encrypt = sys.argv[1]
        encrypted = encrypt_api_key(key_to_encrypt)
        print(f"Encrypted key:\n{encrypted}")
    else:
        print("Usage: python secrets.py <api_key_to_encrypt>")
