from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from kis_collect import KST, KisClient, daily_price, load_universe


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["1540", "close", "manual"])
    p.add_argument("--universe", default="universe.csv")
    args = p.parse_args()

    today = datetime.now(KST).strftime("%Y%m%d")
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        print(json.dumps({"state": "unknown", "reason": "KIS secrets missing"}))
        return 2

    try:
        universe = load_universe(args.universe)
        probe_code = str(universe.iloc[0]["code"])
        client = KisClient(app_key, app_secret)
        client.auth()
        rows = daily_price(client, probe_code)
        dates = [str(x.get("stck_bsop_date", "")) for x in rows if x.get("stck_bsop_date")]
        latest = max(dates) if dates else ""
    except Exception as e:
        print(json.dumps({"state": "unknown", "today": today, "error": str(e)}, ensure_ascii=False))
        return 2

    state = "open" if latest == today else "closed"
    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": args.mode,
        "today": today,
        "latest_market_date": latest,
        "state": state,
    }
    out = Path("data")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"latest_{args.mode}_market_day.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False))
    return 0 if state == "open" else 10


if __name__ == "__main__":
    raise SystemExit(main())
