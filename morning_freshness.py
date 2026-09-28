from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from kis_collect import KST


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-age-min", type=int, default=15)
    args = p.parse_args()

    path = Path("data/latest_manual_status.json")
    if not path.exists():
        print(json.dumps({"ok": False, "reason": "missing latest_manual_status.json"}, ensure_ascii=False))
        return 1

    try:
        status = json.loads(path.read_text(encoding="utf-8"))
        snap = datetime.fromisoformat(str(status.get("snapshot_kst", "")))
    except Exception as e:
        print(json.dumps({"ok": False, "reason": f"invalid status: {e}"}, ensure_ascii=False))
        return 1

    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    market_date = str(status.get("market_date", ""))
    age_min = (now - snap.astimezone(KST)).total_seconds() / 60.0
    full_ok = bool(status.get("full_field_coverage_ok"))

    ok = market_date == today and full_ok and 0 <= age_min <= args.max_age_min
    print(json.dumps({
        "ok": ok,
        "market_date": market_date,
        "today": today,
        "age_min": round(age_min, 1),
        "full_field_coverage_ok": full_ok,
        "snapshot_kst": status.get("snapshot_kst"),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
