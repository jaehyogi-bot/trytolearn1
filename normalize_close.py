from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from kis_collect import KST, KisClient, daily_chart, daily_price, n, ratio, pct

PRICE_BASIS = "KRX_regular_close_daily"
SLEEP_SEC = 0.20


def _avg(values: list[float | None]) -> float | None:
    xs = [x for x in values if x is not None]
    return sum(xs) / len(xs) if xs else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="data/latest_close.csv")
    args = p.parse_args()

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        print("ERROR: KIS_APP_KEY / KIS_APP_SECRET are required", file=sys.stderr)
        return 2

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: missing {path}", file=sys.stderr)
        return 3

    df = pd.read_csv(path, dtype={"code": str})
    if df.empty:
        print("ERROR: empty close snapshot", file=sys.stderr)
        return 4
    df["code"] = df["code"].astype(str).str.zfill(6)

    client = KisClient(app_key, app_secret)
    client.auth()

    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    start_date = (now - timedelta(days=45)).strftime("%Y%m%d")
    failures: list[dict[str, str]] = []
    normalized = 0

    for idx, row in df.iterrows():
        code = str(row["code"]).zfill(6)
        name = str(row.get("name", code))
        try:
            daily = daily_price(client, code)
            time.sleep(SLEEP_SEC)
            chart = daily_chart(client, code, start_date, today)
            time.sleep(SLEEP_SEC)

            d = [x for x in daily if x.get("stck_bsop_date")]
            d.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
            if not d:
                raise RuntimeError("daily price response empty")
            latest = d[0]
            market_date = str(latest.get("stck_bsop_date", ""))
            if market_date != today:
                raise RuntimeError(f"latest KRX daily date {market_date} != {today}")

            close = n(latest.get("stck_clpr"))
            opn = n(latest.get("stck_oprc"))
            high = n(latest.get("stck_hgpr"))
            low = n(latest.get("stck_lwpr"))
            vol = n(latest.get("acml_vol"))
            change_pct = n(latest.get("prdy_ctrt"))
            if None in (close, opn, high, low, vol):
                raise RuntimeError("KRX daily OHLCV incomplete")

            prev_vol = n(d[1].get("acml_vol")) if len(d) > 1 else None
            avg20_vol = _avg([n(x.get("acml_vol")) for x in d[1:21]])
            c5 = n(d[5].get("stck_clpr")) if len(d) > 5 else None
            c20 = n(d[20].get("stck_clpr")) if len(d) > 20 else None

            chart_rows = [x for x in chart[1] if x.get("stck_bsop_date")]
            chart_rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
            today_chart = next((x for x in chart_rows if str(x.get("stck_bsop_date", "")) == market_date), {})
            hist_chart = [x for x in chart_rows if str(x.get("stck_bsop_date", "")) != market_date]
            turnover = n(today_chart.get("acml_tr_pbmn"))
            if turnover is None:
                turnover = n(row.get("turnover_value_raw"))
            prev_turnover = n(hist_chart[0].get("acml_tr_pbmn")) if hist_chart else None
            avg20_turnover = _avg([n(x.get("acml_tr_pbmn")) for x in hist_chart[:20]])

            close_pos = None
            upper_wick = None
            if high != low:
                close_pos = (close - low) / (high - low) * 100.0
                upper_wick = (high - max(close, opn)) / (high - low) * 100.0

            listed_shares = n(row.get("listed_shares"))
            market_cap = close * listed_shares if listed_shares not in (None, 0) else None
            weighted = turnover / vol if turnover is not None and vol not in (None, 0) else None
            turnover_to_mcap = turnover / market_cap * 100.0 if turnover is not None and market_cap not in (None, 0) else None
            volume_turnover = vol / listed_shares * 100.0 if listed_shares not in (None, 0) else None

            updates = {
                "snapshot_kst": now.isoformat(timespec="seconds"),
                "market_date": market_date,
                "price": close,
                "change_pct": change_pct,
                "open": opn,
                "high": high,
                "low": low,
                "close_position_pct": close_pos,
                "upper_wick_pct": upper_wick,
                "volume": vol,
                "prev_volume": prev_vol,
                "volume_vs_prev_x": ratio(vol, prev_vol),
                "avg20_volume": avg20_vol,
                "volume_vs_20d_x": ratio(vol, avg20_vol),
                "turnover_value_raw": turnover,
                "prev_turnover_value_raw": prev_turnover,
                "turnover_vs_prev_x": ratio(turnover, prev_turnover),
                "avg20_turnover_value_raw": avg20_turnover,
                "turnover_vs_20d_x": ratio(turnover, avg20_turnover),
                "market_cap_est_won": market_cap,
                "weighted_avg_price": weighted,
                "turnover_value_est_won": turnover,
                "turnover_to_mcap_pct": turnover_to_mcap,
                "volume_turnover_pct": volume_turnover,
                "return_5d_pct": pct(close, c5),
                "return_20d_pct": pct(close, c20),
                "price2_prev_volume_ratio_pct": ratio(vol, prev_vol) * 100.0 if ratio(vol, prev_vol) is not None else None,
            }
            for col, value in updates.items():
                if col in df.columns:
                    df.at[idx, col] = value
            normalized += 1
            print(f"[{idx+1:02d}/{len(df)}] KRX CLOSE OK {name} {code}")
        except Exception as exc:
            failures.append({"name": name, "code": code, "error": str(exc)})
            print(f"[{idx+1:02d}/{len(df)}] KRX CLOSE FAIL {name} {code}: {exc}", file=sys.stderr)

    if failures:
        print(json.dumps({"normalized": normalized, "failures": failures}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 5

    market_date = today
    out_dir = Path("data")
    dated = out_dir / f"{market_date}_close.csv"
    latest = out_dir / "latest_close.csv"
    df.to_csv(dated, index=False, encoding="utf-8-sig")
    df.to_csv(latest, index=False, encoding="utf-8-sig")

    status_path = out_dir / "latest_close_status.json"
    status = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    status.update({
        "snapshot_kst": now.isoformat(timespec="seconds"),
        "mode": "close",
        "market_date": market_date,
        "price_basis": PRICE_BASIS,
        "normalized_count": normalized,
        "normalized_failure_count": 0,
        "normalized_at_kst": now.isoformat(timespec="seconds"),
    })
    status_text = json.dumps(status, ensure_ascii=False, indent=2)
    status_path.write_text(status_text, encoding="utf-8")
    (out_dir / f"{market_date}_close_status.json").write_text(status_text, encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "market_date": market_date,
        "normalized_count": normalized,
        "price_basis": PRICE_BASIS,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
