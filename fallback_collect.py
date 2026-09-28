from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from kis_collect import KST, load_universe

TIMEOUT = 15
SLEEP_SEC = 0.08


def num(v: Any) -> float | None:
    if v in (None, "", "-"):
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    s = re.sub(r"[^0-9.+-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def fetch_naver_basic(session: requests.Session, code: str) -> dict[str, Any]:
    url = f"https://m.stock.naver.com/api/stock/{code}/basic"
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if not isinstance(body, dict):
        raise RuntimeError("unexpected Naver response")
    return body


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["1540", "close", "manual"])
    p.add_argument("--universe", default="universe.csv")
    args = p.parse_args()

    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    universe = load_universe(args.universe)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; portfolio-risk-monitor/1.0)",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://m.stock.naver.com/",
    })

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for i, r in universe.iterrows():
        code = str(r["code"])
        name = str(r["name"])
        group = str(r["group"])
        try:
            body = fetch_naver_basic(session, code)
            price = num(pick(body, "closePrice", "close_price", "currentPrice", "nowVal"))
            if price is None:
                raise RuntimeError("price missing")

            rows.append({
                "snapshot_kst": now.isoformat(timespec="seconds"),
                "mode": args.mode,
                "market_date": today,
                "name": pick(body, "stockName", "itemName", "name") or name,
                "code": code,
                "group": group,
                "source": "naver_mobile_fallback",
                "price": price,
                "change_pct": num(pick(body, "fluctuationsRatio", "changeRate", "rate")),
                "volume": num(pick(body, "accumulatedTradingVolume", "accumulatedVolume", "volume")),
                "turnover_value_raw": num(pick(body, "accumulatedTradingValue", "accumulatedTradingAmount", "tradingValue")),
                "market_cap_est_won": num(pick(body, "marketValue", "marketCap", "marketValueWon")),
                "fallback_note": "Primary KIS snapshot missing/stale/incomplete; minimal public-web core fields only",
            })
            print(f"[{i+1:02d}/{len(universe)}] FALLBACK OK {name} {code}")
        except Exception as e:
            failures.append({"name": name, "code": code, "error": str(e)})
            print(f"[{i+1:02d}/{len(universe)}] FALLBACK FAIL {name} {code}: {e}")
        time.sleep(SLEEP_SEC)

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(out_dir / f"{today}_{args.mode}_fallback.csv", index=False, encoding="utf-8-sig")
        df.to_csv(out_dir / f"latest_{args.mode}_fallback.csv", index=False, encoding="utf-8-sig")

    coverage_ok = len(rows) == len(universe) and not failures
    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": args.mode,
        "market_date": today,
        "source": "naver_mobile_fallback",
        "universe_count": int(len(universe)),
        "success_count": len(rows),
        "failure_count": len(failures),
        "failures": failures,
        "coverage_ok": coverage_ok,
        "degraded": True,
        "note": "Fallback contains only core public-web fields, not KIS investor/short/loan auxiliary fields.",
    }
    text = json.dumps(status, ensure_ascii=False, indent=2)
    (out_dir / f"{today}_{args.mode}_fallback_status.json").write_text(text, encoding="utf-8")
    (out_dir / f"latest_{args.mode}_fallback_status.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if coverage_ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
