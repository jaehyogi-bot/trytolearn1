from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE_URL = "https://openapi.koreainvestment.com:9443"
KST = ZoneInfo("Asia/Seoul")
TIMEOUT = 20
SLEEP_SEC = 0.22


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
        self.token = r.json()["access_token"]

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


def ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def sum_n(values: list[float | None], count: int) -> float | None:
    xs = [x for x in values[:count] if x is not None]
    return sum(xs) if xs else None


def consecutive_positive(values: list[float | None]) -> int:
    c = 0
    for v in values:
        if v is not None and v > 0:
            c += 1
        else:
            break
    return c


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


def current_price_basic(client: KisClient, code: str) -> dict[str, Any]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
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


def daily_chart(client: KisClient, code: str, start_date: str, end_date: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        "FHKST03010100",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1",
        },
    )
    out1 = body.get("output1", {}) or {}
    out2 = body.get("output2", []) or []
    if isinstance(out2, dict):
        out2 = [out2]
    return out1, out2


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


def daily_short_sale(client: KisClient, code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/daily-short-sale",
        "FHPST04830000",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
        },
    )
    out = body.get("output2", []) or []
    if isinstance(out, dict):
        out = [out]
    return out


def daily_loan_trans(client: KisClient, code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/daily-loan-trans",
        "HHPST074500C0",
        {
            "MRKT_DIV_CLS_CODE": "3",
            "MKSC_SHRN_ISCD": code,
            "START_DATE": start_date,
            "END_DATE": end_date,
            "CTS": "",
        },
    )
    out = body.get("output1", []) or []
    if isinstance(out, dict):
        out = [out]
    return out


def optional_call(label: str, fn, aux_failures: list[dict[str, str]], name: str, code: str):
    try:
        result = fn()
        time.sleep(SLEEP_SEC)
        return result
    except Exception as e:
        aux_failures.append({"name": name, "code": code, "field": label, "error": str(e)})
        return None


def summarize(
    name: str,
    code: str,
    group: str,
    cur: dict[str, Any],
    basic: dict[str, Any] | None,
    daily: list[dict[str, Any]],
    chart: tuple[dict[str, Any], list[dict[str, Any]]] | None,
    inv: list[dict[str, Any]] | None,
    shorts: list[dict[str, Any]] | None,
    loans: list[dict[str, Any]] | None,
    mode: str,
    aux_missing: list[str],
) -> dict[str, Any]:
    d = [x for x in daily if x.get("stck_bsop_date")]
    d.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
    latest = d[0] if d else {}
    market_date = str(latest.get("stck_bsop_date", ""))

    basic = basic or {}
    close = n(cur.get("stck_prpr")) or n(basic.get("stck_prpr")) or n(latest.get("stck_clpr"))
    opn = n(cur.get("stck_oprc")) or n(basic.get("stck_oprc")) or n(latest.get("stck_oprc"))
    high = n(cur.get("stck_hgpr")) or n(basic.get("stck_hgpr")) or n(latest.get("stck_hgpr"))
    low = n(cur.get("stck_lwpr")) or n(basic.get("stck_lwpr")) or n(latest.get("stck_lwpr"))
    vol = n(cur.get("acml_vol")) or n(basic.get("acml_vol")) or n(latest.get("acml_vol"))
    prev_vol = n(cur.get("prdy_vol")) or (n(d[1].get("acml_vol")) if len(d) > 1 else None)
    turnover_raw = n(cur.get("acml_tr_pbmn")) or n(basic.get("acml_tr_pbmn"))
    change_pct = n(cur.get("prdy_ctrt")) or n(basic.get("prdy_ctrt")) or n(latest.get("prdy_ctrt"))

    hist_daily = d[1:] if d and str(d[0].get("stck_bsop_date", "")) == market_date else d
    vols = [n(x.get("acml_vol")) for x in hist_daily[:20]]
    vols = [x for x in vols if x is not None]
    avg20_vol = sum(vols) / len(vols) if vols else None
    c5 = n(d[5].get("stck_clpr")) if len(d) > 5 else None
    c20 = n(d[20].get("stck_clpr")) if len(d) > 20 else None

    close_pos = None
    upper_wick_pct = None
    if None not in (close, high, low) and high != low:
        close_pos = (close - low) / (high - low) * 100.0
        upper_wick_pct = (high - max(close, opn or close)) / (high - low) * 100.0

    chart_rows: list[dict[str, Any]] = []
    if chart:
        chart_rows = [x for x in chart[1] if x.get("stck_bsop_date")]
        chart_rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
    hist_chart = [x for x in chart_rows if str(x.get("stck_bsop_date", "")) != market_date]
    prev_turnover = n(hist_chart[0].get("acml_tr_pbmn")) if hist_chart else None
    turn20 = [n(x.get("acml_tr_pbmn")) for x in hist_chart[:20]]
    turn20 = [x for x in turn20 if x is not None]
    avg20_turnover = sum(turn20) / len(turn20) if turn20 else None

    inv_rows = [x for x in (inv or []) if x.get("stck_bsop_date")]
    inv_rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
    frgn_qty = [n(x.get("frgn_ntby_qty")) for x in inv_rows]
    orgn_qty = [n(x.get("orgn_ntby_qty")) for x in inv_rows]
    frgn_amt = [n(x.get("frgn_ntby_tr_pbmn")) for x in inv_rows]
    orgn_amt = [n(x.get("orgn_ntby_tr_pbmn")) for x in inv_rows]

    short_rows = [x for x in (shorts or []) if x.get("stck_bsop_date")]
    short_rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
    short_qty = [n(x.get("ssts_cntg_qty")) for x in short_rows]
    short_value = [n(x.get("ssts_tr_pbmn")) for x in short_rows]

    loan_rows = [x for x in (loans or []) if x.get("bsop_date")]
    loan_rows.sort(key=lambda x: x["bsop_date"], reverse=True)
    loan_change = [n(x.get("prdy_rmnd_vrss")) for x in loan_rows]

    listed_shares = n(basic.get("lstn_stcn"))
    weighted_price = n(basic.get("wghn_avrg_stck_prc"))
    market_cap_est_won = close * listed_shares if close is not None and listed_shares is not None else None
    turnover_est_won = weighted_price * vol if weighted_price is not None and vol is not None else None
    turnover_to_mcap_pct = (
        turnover_est_won / market_cap_est_won * 100.0
        if turnover_est_won is not None and market_cap_est_won not in (None, 0)
        else None
    )

    return {
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
        "close_position_pct": close_pos,
        "upper_wick_pct": upper_wick_pct,
        "volume": vol,
        "prev_volume": prev_vol,
        "volume_vs_prev_x": ratio(vol, prev_vol),
        "avg20_volume": avg20_vol,
        "volume_vs_20d_x": ratio(vol, avg20_vol),
        "turnover_value_raw": turnover_raw,
        "prev_turnover_value_raw": prev_turnover,
        "turnover_vs_prev_x": ratio(turnover_raw, prev_turnover),
        "avg20_turnover_value_raw": avg20_turnover,
        "turnover_vs_20d_x": ratio(turnover_raw, avg20_turnover),
        "listed_shares": listed_shares,
        "market_cap_est_won": market_cap_est_won,
        "weighted_avg_price": weighted_price,
        "turnover_value_est_won": turnover_est_won,
        "turnover_to_mcap_pct": turnover_to_mcap_pct,
        "volume_turnover_pct": n(basic.get("vol_tnrt")),
        "return_5d_pct": pct(close, c5),
        "return_20d_pct": pct(close, c20),
        "foreign_today_qty": frgn_qty[0] if frgn_qty else None,
        "institution_today_qty": orgn_qty[0] if orgn_qty else None,
        "foreign_today_value_raw": frgn_amt[0] if frgn_amt else None,
        "institution_today_value_raw": orgn_amt[0] if orgn_amt else None,
        "foreign_5d_qty": sum_n(frgn_qty, 5),
        "institution_5d_qty": sum_n(orgn_qty, 5),
        "foreign_20d_qty": sum_n(frgn_qty, 20),
        "institution_20d_qty": sum_n(orgn_qty, 20),
        "foreign_5d_value_raw": sum_n(frgn_amt, 5),
        "institution_5d_value_raw": sum_n(orgn_amt, 5),
        "foreign_buy_streak": consecutive_positive(frgn_qty),
        "institution_buy_streak": consecutive_positive(orgn_qty),
        "program_today_qty": n(basic.get("pgtr_ntby_qty")),
        "short_today_qty": short_qty[0] if short_qty else None,
        "short_today_value_raw": short_value[0] if short_value else None,
        "short_today_volume_pct": n(short_rows[0].get("ssts_vol_rlim")) if short_rows else None,
        "short_today_value_pct": n(short_rows[0].get("ssts_tr_pbmn_rlim")) if short_rows else None,
        "short_5d_qty": sum_n(short_qty, 5),
        "short_20d_qty": sum_n(short_qty, 20),
        "short_5d_value_raw": sum_n(short_value, 5),
        "short_20d_value_raw": sum_n(short_value, 20),
        "loan_today_change_qty": loan_change[0] if loan_change else None,
        "loan_5d_change_qty": sum_n(loan_change, 5),
        "loan_20d_change_qty": sum_n(loan_change, 20),
        "loan_balance_qty": n(loan_rows[0].get("rmnd_stcn")) if loan_rows else None,
        "loan_balance_value_raw": n(loan_rows[0].get("rmnd_amt")) if loan_rows else None,
        "whole_credit_balance_ratio": n(basic.get("whol_loan_rmnd_rate")),
        "per": n(basic.get("per")),
        "pbr": n(basic.get("pbr")),
        "eps": n(basic.get("eps")),
        "bps": n(basic.get("bps")),
        "price2_prev_volume_ratio_pct": n(cur.get("prdy_vrss_vol_rate")),
        "trading_halt": cur.get("trht_yn"),
        "short_overheat": cur.get("ssts_hot_yn"),
        "shortable": basic.get("ssts_yn"),
        "aux_missing": "|".join(sorted(set(aux_missing))),
    }


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

    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    start_date = (now - timedelta(days=45)).strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []
    core_failures: list[dict[str, str]] = []
    aux_failures: list[dict[str, str]] = []

    for i, r in u.iterrows():
        name, code, group = str(r["name"]), str(r["code"]), str(r["group"])
        try:
            cur = current_price(client, code)
            time.sleep(SLEEP_SEC)
            daily = daily_price(client, code)
            time.sleep(SLEEP_SEC)
        except Exception as e:
            core_failures.append({"name": name, "code": code, "error": str(e)})
            print(f"[{i+1:02d}/{len(u)}] CORE FAIL {name} {code}: {e}", file=sys.stderr)
            continue

        aux_before = len(aux_failures)
        basic = optional_call("basic", lambda: current_price_basic(client, code), aux_failures, name, code)
        chart = optional_call("daily_chart", lambda: daily_chart(client, code, start_date, today), aux_failures, name, code)
        inv = optional_call("investor", lambda: investor_daily(client, code, today), aux_failures, name, code)
        shorts = optional_call("short_sale", lambda: daily_short_sale(client, code, start_date, today), aux_failures, name, code)
        loans = optional_call("loan", lambda: daily_loan_trans(client, code, start_date, today), aux_failures, name, code)
        aux_missing = [x["field"] for x in aux_failures[aux_before:]]

        rows.append(summarize(name, code, group, cur, basic, daily, chart, inv, shorts, loans, args.mode, aux_missing))
        print(f"[{i+1:02d}/{len(u)}] OK {name} {code}" + (f" AUX_MISSING={','.join(aux_missing)}" if aux_missing else ""))

    if not rows:
        print("ERROR: no rows collected", file=sys.stderr)
        return 3

    market_dates = sorted({str(x.get("market_date", "")) for x in rows if x.get("market_date")})
    market_date = market_dates[-1] if market_dates else today
    if args.mode in {"1540", "close"} and market_date != today:
        print(f"SKIP: KRX appears closed. latest market date={market_date}, today={today}")
        return 0

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / f"{market_date}_{args.mode}.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out_dir / f"latest_{args.mode}.csv", index=False, encoding="utf-8-sig")

    core_ok = len(rows) == len(u) and not core_failures
    full_ok = core_ok and not aux_failures
    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": args.mode,
        "market_date": market_date,
        "universe_count": int(len(u)),
        "success_count": len(rows),
        "core_failure_count": len(core_failures),
        "aux_failure_count": len(aux_failures),
        "core_failures": core_failures,
        "aux_failures": aux_failures,
        "core_coverage_ok": core_ok,
        "full_field_coverage_ok": full_ok,
        "coverage_ok": full_ok,
        "coverage_rule": "전체 스캔 완료 표현은 full_field_coverage_ok=true일 때만 사용",
    }
    text = json.dumps(status, ensure_ascii=False, indent=2)
    (out_dir / f"{market_date}_{args.mode}_status.json").write_text(text, encoding="utf-8")
    (out_dir / f"latest_{args.mode}_status.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if core_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
