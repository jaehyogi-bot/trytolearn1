from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE_URL = "https://openapi.koreainvestment.com:9443"
KST = ZoneInfo("Asia/Seoul")
TIMEOUT = 20
SLEEP_SEC = 0.18


@dataclass
class KisClient:
    app_key: str
    app_secret: str
    token: str = ""

    def auth(self) -> None:
        r = requests.post(
            f"{BASE_URL}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
        self.token = body["access_token"]

    def get(self, path: str, tr_id: str, params: dict[str, str], retries: int = 4) -> dict[str, Any]:
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=TIMEOUT)
                if r.status_code == 401:
                    self.auth()
                    headers["authorization"] = f"Bearer {self.token}"
                    continue
                r.raise_for_status()
                body = r.json()
                if body.get("rt_cd") == "0":
                    return body
                msg_cd = body.get("msg_cd", "")
                msg = body.get("msg1", "")
                if msg_cd == "EGW00201" or "초당" in msg or "rate" in msg.lower():
                    time.sleep(1.0 + attempt)
                    continue
                raise RuntimeError(f"KIS error {msg_cd}: {msg}")
            except Exception as e:
                last_err = e
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"KIS request failed: {path} {params} / {last_err}")


def n(v: Any) -> float | None:
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def load_universe(path: str = "universe.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str})
    df["code"] = df["code"].str.zfill(6)
    df = df[df["active"].astype(str).isin(["1", "True", "true"])]
    return df.reset_index(drop=True)


def current_price(client: KisClient, code: str) -> dict[str, Any]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-price-2",
        "FHPST01010000",
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
    )
    return body.get("output", {}) or {}


def daily_price(client: KisClient, code: str) -> list[dict[str, Any]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
        "FHKST01010400",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1",
        },
    )
    return body.get("output", []) or []


def investor_daily(client: KisClient, code: str, yyyymmdd: str) -> list[dict[str, Any]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
        "FHPTJ04160001",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": yyyymmdd,
            "FID_ORG_ADJ_PRC": "",
            "FID_ETC_CLS_CODE": "",
        },
    )
    out = body.get("output1", []) or []
    if isinstance(out, dict):
        out = [out]
    return out


def consecutive_positive(values: list[float | None]) -> int:
    c = 0
    for v in values:
        if v is not None and v > 0:
            c += 1
        else:
            break
    return c


def summarize(name: str, code: str, group: str, cur: dict[str, Any], daily: list[dict[str, Any]], inv: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    d = [x for x in daily if x.get("stck_bsop_date")]
    d.sort(key=lambda x: x["stck_bsop_date"], reverse=True)

    latest = d[0] if d else {}
    market_date = latest.get("stck_bsop_date", "")

    close = n(cur.get("stck_prpr")) or n(latest.get("stck_clpr"))
    opn = n(cur.get("stck_oprc")) or n(latest.get("stck_oprc"))
    high = n(cur.get("stck_hgpr")) or n(latest.get("stck_hgpr"))
    low = n(cur.get("stck_lwpr")) or n(latest.get("stck_lwpr"))
    vol = n(cur.get("acml_vol")) or n(latest.get("acml_vol"))
    prev_vol = n(cur.get("prdy_vol")) or (n(d[1].get("acml_vol")) if len(d) > 1 else None)
    turnover = n(cur.get("acml_tr_pbmn"))
    change_pct = n(cur.get("prdy_ctrt")) or n(latest.get("prdy_ctrt"))

    vols = [n(x.get("acml_vol")) for x in d[1:21]]
    vols = [x for x in vols if x is not None]
    avg20_vol = sum(vols) / len(vols) if vols else None

    c5 = n(d[5].get("stck_clpr")) if len(d) > 5 else None
    c20 = n(d[20].get("stck_clpr")) if len(d) > 20 else None
    ret5 = pct(close, c5)
    ret20 = pct(close, c20)

    close_pos = None
    upper_wick_pct = None
    if None not in (close, high, low) and high != low:
        close_pos = (close - low) / (high - low) * 100.0
        upper_wick_pct = (high - max(close, opn or close)) / (high - low) * 100.0

    inv_rows = [x for x in inv if x.get("stck_bsop_date")]
    inv_rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
    frgn = [n(x.get("frgn_ntby_qty")) for x in inv_rows]
    orgn = [n(x.get("orgn_ntby_qty")) for x in inv_rows]

    def sum_n(xs: list[float | None], count: int) -> float | None:
        ys = [x for x in xs[:count] if x is not None]
        return sum(ys) if ys else None

    row = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": mode,
        "market_date": market_date,
        "name": name,
        "code": code,
        "group": group,
        "price": close,
        "change_pct": change_pct,
        "open": opn,
        "high": high,
        "low": low,
        "volume": vol,
        "prev_volume": prev_vol,
        "volume_vs_prev_x": (vol / prev_vol if vol is not None and prev_vol not in (None, 0) else None),
        "avg20_volume": avg20_vol,
        "volume_vs_20d_x": (vol / avg20_vol if vol is not None and avg20_vol not in (None, 0) else None),
        "turnover_value": turnover,
        "close_position_pct": close_pos,
        "upper_wick_pct": upper_wick_pct,
        "return_5d_pct": ret5,
        "return_20d_pct": ret20,
        "foreign_today_qty": frgn[0] if frgn else None,
        "institution_today_qty": orgn[0] if orgn else None,
        "foreign_5d_qty": sum_n(frgn, 5),
        "institution_5d_qty": sum_n(orgn, 5),
        "foreign_20d_qty": sum_n(frgn, 20),
        "institution_20d_qty": sum_n(orgn, 20),
        "foreign_buy_streak": consecutive_positive(frgn),
        "institution_buy_streak": consecutive_positive(orgn),
        "price2_prev_volume_ratio_pct": n(cur.get("prdy_vrss_vol_rate")),
        "trading_halt": cur.get("trht_yn"),
        "short_overheat": cur.get("ssts_hot_yn"),
    }
    return row


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["1540", "close", "manual"], default="manual")
    p.add_argument("--universe", default="universe.csv")
    args = p.parse_args()

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        print("ERROR: KIS_APP_KEY / KIS_APP_SECRET are required", file=sys.stderr)
        return 2

    u = load_universe(args.universe)
    client = KisClient(app_key, app_secret)
    client.auth()

    today = datetime.now(KST).strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for i, r in u.iterrows():
        name, code, group = str(r["name"]), str(r["code"]), str(r["group"])
        try:
            cur = current_price(client, code)
            time.sleep(SLEEP_SEC)
            daily = daily_price(client, code)
            time.sleep(SLEEP_SEC)
            inv = investor_daily(client, code, today)
            time.sleep(SLEEP_SEC)
            rows.append(summarize(name, code, group, cur, daily, inv, args.mode))
            print(f"[{i+1:02d}/{len(u)}] OK {name} {code}")
        except Exception as e:
            failures.append({"name": name, "code": code, "error": str(e)})
            print(f"[{i+1:02d}/{len(u)}] FAIL {name} {code}: {e}", file=sys.stderr)

    if not rows:
        print("ERROR: no rows collected", file=sys.stderr)
        return 3

    market_dates = sorted({str(x.get("market_date", "")) for x in rows if x.get("market_date")})
    market_date = market_dates[-1] if market_dates else today

    # 휴장일에는 전 거래일 데이터를 오늘 데이터처럼 중복 저장하지 않는다.
    if args.mode in {"1540", "close"} and market_date != today:
        print(f"SKIP: KRX appears closed. latest market date={market_date}, today={today}")
        return 0

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{market_date}_{args.mode}.csv"
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")

    # 최신 파일: ChatGPT에서 매번 날짜를 몰라도 쉽게 읽기 위한 포인터 역할.
    latest = out_dir / f"latest_{args.mode}.csv"
    pd.DataFrame(rows).to_csv(latest, index=False, encoding="utf-8-sig")

    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": args.mode,
        "market_date": market_date,
        "universe_count": int(len(u)),
        "success_count": len(rows),
        "failure_count": len(failures),
        "failures": failures,
        "coverage_ok": len(rows) == len(u),
    }
    (out_dir / f"{market_date}_{args.mode}_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"latest_{args.mode}_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if not failures else 4


if __name__ == "__main__":
    raise SystemExit(main())
