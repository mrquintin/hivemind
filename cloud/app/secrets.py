"""
Secure storage for sensitive API keys.
Keys are encrypted using Fernet symmetric encryption.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.runtime_paths import api_key_file

# Encryption key derived from a fixed salt (the actual security comes from
# the encrypted value being meaningless without this code + the salt)
_SALT = b"hivemind_secure_key_storage_v1"


def _get_cipher() -> Fernet:
    """Create a Fernet cipher using a deterministic key derived from the salt."""
    # Derive a 32-byte key from the salt using SHA-256
    key_material = hashlib.sha256(_SALT).digest()
    fernet_key = base64.urlsafe_b64encode(key_material)
    return Fernet(fernet_key)


def decrypt_api_key(encrypted_value: str) -> str:
    """Decrypt an API key that was encrypted with encrypt_api_key()."""
    cipher = _get_cipher()
    decrypted = cipher.decrypt(encrypted_value.encode())
    return decrypted.decode()


def encrypt_api_key(plain_value: str) -> str:
    """Encrypt an API key for storage. Used once to generate the encrypted value."""
    cipher = _get_cipher()
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
