from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import kis_collect
from kis_token_store import load_token, save_token


def _parse_expiry(body: dict[str, Any], issued_at: datetime) -> datetime:
    raw = str(body.get("access_token_token_expired", "")).strip()
    if raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=kis_collect.KST)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=kis_collect.KST)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

    try:
        seconds = int(body.get("expires_in", 86400))
    except (TypeError, ValueError):
        seconds = 86400
    return issued_at + timedelta(seconds=max(seconds, 60))


def _install_cached_auth() -> None:
    def cached_auth(self: kis_collect.KisClient) -> None:
        # Normal startup: reuse the encrypted cache if it is still valid.
        if not self.token:
            cached = load_token(self.app_secret)
            if cached:
                self.token = str(cached["access_token"])
                print(f"KIS_AUTH=CACHE expires_at={cached.get('expires_at', '')}")
                return

        # If auth() is called while a token is already set, KisClient.get() saw a 401.
        # Permit at most one real issuance in a process so a bad response cannot cause
        # repeated token issuance loops.
        if getattr(self, "_kis_token_issued_this_process", False):
            raise RuntimeError("KIS token was already issued once in this process; refusing repeated issuance")

        issued_at = datetime.now(timezone.utc)
        response = requests.post(
            f"{kis_collect.BASE_URL}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=kis_collect.TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        token = str(body.get("access_token", "")).strip()
        if not token:
            raise RuntimeError(f"KIS token response missing access_token: {json.dumps(body, ensure_ascii=False)[:500]}")

        expires_at = _parse_expiry(body, issued_at)
        self.token = token
        self._kis_token_issued_this_process = True
        save_token(self.app_secret, token, expires_at, issued_at)
        print(f"KIS_AUTH=ISSUED expires_at={expires_at.isoformat(timespec='seconds')}")

    kis_collect.KisClient.auth = cached_auth


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python kis_runner.py {collect|market-day-check|discovery} [args...]", file=sys.stderr)
        return 2

    command = sys.argv[1]
    rest = sys.argv[2:]
    targets = {
        "collect": "kis_collect",
        "market-day-check": "market_day_check",
        "discovery": "market_discovery",
    }
    module_name = targets.get(command)
    if not module_name:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 2

    _install_cached_auth()
    module = kis_collect if module_name == "kis_collect" else importlib.import_module(module_name)

    old_argv = sys.argv
    try:
        sys.argv = [f"{module_name}.py", *rest]
        return int(module.main())
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
