from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def primary_status(mode: str) -> tuple[bool, str, dict]:
    today = datetime.now(KST).strftime("%Y%m%d")
    path = Path("data") / f"latest_{mode}_status.json"
    if not path.exists():
        return False, f"missing {path}", {}

    status = load_json(path)
    requested_date = str(status.get("requested_date", ""))
    market_date = str(status.get("market_date", ""))

    if status.get("market_closed") is True and requested_date == today:
        return True, f"KRX closed for {today}; latest market date={market_date}", status

    if market_date != today:
        return False, f"stale primary data: market_date={market_date or 'missing'}, today={today}", status

    if not bool(status.get("core_coverage_ok")):
        return False, "primary core coverage incomplete", status

    return True, "primary core data fresh", status


def full_status(mode: str) -> tuple[bool, str, dict]:
    ok, reason, status = primary_status(mode)
    if not ok:
        return ok, reason, status
    if status.get("market_closed") is True:
        return True, reason, status
    if not bool(status.get("full_field_coverage_ok")):
        return False, "primary auxiliary fields incomplete", status
    return True, "primary full-field data fresh", status


def fallback_status(mode: str) -> tuple[bool, str, dict]:
    today = datetime.now(KST).strftime("%Y%m%d")
    path = Path("data") / f"latest_{mode}_fallback_status.json"
    if not path.exists():
        return False, f"missing {path}", {}
    status = load_json(path)
    if str(status.get("market_date", "")) != today:
        return False, f"stale fallback data: {status.get('market_date')} != {today}", status
    if not bool(status.get("coverage_ok")):
        return False, "fallback coverage incomplete", status
    return True, "fallback core data fresh", status


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["1540", "close", "manual"])
    p.add_argument("--require", choices=["full", "core", "fallback"], default="full")
    args = p.parse_args()

    if args.require == "full":
        ok, reason, status = full_status(args.mode)
    elif args.require == "core":
        ok, reason, status = primary_status(args.mode)
    else:
        ok, reason, status = fallback_status(args.mode)

    print(json.dumps({
        "ok": ok,
        "mode": args.mode,
        "require": args.require,
        "reason": reason,
        "status": status,
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
