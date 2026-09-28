from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_CACHE_PATH = Path("data/.kis_token_cache.enc")
CACHE_VERSION = 1


def _cache_path() -> Path:
    return Path(os.getenv("KIS_TOKEN_CACHE_FILE", str(DEFAULT_CACHE_PATH)))


def _fernet(app_secret: str) -> Fernet:
    # KIS app secret is high entropy. Derive a separate key so the app secret itself
    # is never written to disk or the repository.
    digest = hashlib.sha256(f"kis-token-cache-v1:{app_secret}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def load_token(app_secret: str) -> dict[str, Any] | None:
    path = _cache_path()
    if not path.exists():
        return None

    try:
        plaintext = _fernet(app_secret).decrypt(path.read_bytes())
        payload = json.loads(plaintext.decode("utf-8"))
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError):
        return None

    if payload.get("version") != CACHE_VERSION:
        return None

    token = str(payload.get("access_token", ""))
    expires_at = str(payload.get("expires_at", ""))
    if not token or not expires_at:
        return None

    try:
        expiry = datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    if expiry <= datetime.now(timezone.utc):
        return None

    return payload


def save_token(app_secret: str, access_token: str, expires_at: datetime, issued_at: datetime) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    expiry = expires_at.astimezone(timezone.utc)
    issued = issued_at.astimezone(timezone.utc)
    payload = {
        "version": CACHE_VERSION,
        "access_token": access_token,
        "issued_at": issued.isoformat(timespec="seconds"),
        "expires_at": expiry.isoformat(timespec="seconds"),
    }
    ciphertext = _fernet(app_secret).encrypt(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    path.write_bytes(ciphertext)


def cache_metadata(app_secret: str) -> dict[str, str] | None:
    payload = load_token(app_secret)
    if not payload:
        return None
    return {
        "issued_at": str(payload.get("issued_at", "")),
        "expires_at": str(payload.get("expires_at", "")),
    }
