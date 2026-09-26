from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from kis_collect import KST, SLEEP_SEC, KisClient, daily_price, load_universe, n

DEFAULT_CONFIG = {
    "min_market_cap_won": 300_000_000_000,
    "discovery_sort_codes": {
        "volume_increase": "1",
        "turnover": "2",
        "trading_value": "3",
        "trading_value_turnover": "4",
    },
}


def load_config(path: str) -> dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    p = Path(path)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def market_volume_rank(client: KisClient, sort_code: str) -> list[dict[str, Any]]:
    body = client.get(
        "/uapi/domestic-stock/v1/quotations/volume-rank",
        "FHPST01710000",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "1",
            "FID_BLNG_CLS_CODE": sort_code,
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "1000000",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": "",
        },
    )
    out = body.get("output", []) or []
    if isinstance(out, dict):
        out = [out]
    return out


def latest_market_date(client: KisClient, code: str) -> str:
    rows = daily_price(client, code)
    dates = [str(x.get("stck_bsop_date", "")) for x in rows if x.get("stck_bsop_date")]
    return max(dates) if dates else ""


def discover(client: KisClient, universe: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    min_cap = float(cfg.get("min_market_cap_won", DEFAULT_CONFIG["min_market_cap_won"]))
    sort_codes = cfg.get("discovery_sort_codes", DEFAULT_CONFIG["discovery_sort_codes"])
    known = universe.set_index("code").to_dict("index")
    merged: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for signal, sort_code in sort_codes.items():
        try:
            rows = market_volume_rank(client, str(sort_code))
            time.sleep(SLEEP_SEC)
        except Exception as e:
            errors.append(f"{signal}: {e}")
            continue

        for r in rows:
            code = str(r.get("mksc_shrn_iscd", "")).zfill(6)
            if not code or code == "000000":
                continue

            price = n(r.get("stck_prpr"))
            shares = n(r.get("lstn_stcn"))
            market_cap = price * shares if price is not None and shares is not None else None

            # 신규후보 하드필터: 시총 3천억원 미만은 후보 큐에서 제외.
            # 시총 필드가 누락된 경우에는 버리지 않고 미확인으로 남긴다.
            if market_cap is not None and market_cap < min_cap:
                continue

            item = merged.setdefault(
                code,
                {
                    "code": code,
                    "name": r.get("hts_kor_isnm", ""),
                    "signals": [],
                    "best_rank": None,
                    "price": price,
                    "change_pct": n(r.get("prdy_ctrt")),
                    "volume": n(r.get("acml_vol")),
                    "prev_volume": n(r.get("prdy_vol")),
                    "avg_volume": n(r.get("avrg_vol")),
                    "volume_increase_pct": n(r.get("vol_inrt")),
                    "volume_turnover_pct": n(r.get("vol_tnrt")),
                    "turnover_value": n(r.get("acml_tr_pbmn")),
                    "avg_turnover_value": n(r.get("avrg_tr_pbmn")),
                    "turnover_value_turnover_pct": n(r.get("tr_pbmn_tnrt")),
                    "listed_shares": shares,
                    "market_cap_est_won": market_cap,
                    "market_cap_check": "verified" if market_cap is not None else "unverified",
                },
            )

            rank = int(n(r.get("data_rank")) or 9999)
            item["signals"].append(f"{signal}:{rank}")
            if item["best_rank"] is None or rank < item["best_rank"]:
                item["best_rank"] = rank

            for key, field in {
                "price": "stck_prpr",
                "change_pct": "prdy_ctrt",
                "volume": "acml_vol",
                "prev_volume": "prdy_vol",
                "avg_volume": "avrg_vol",
                "volume_increase_pct": "vol_inrt",
                "volume_turnover_pct": "vol_tnrt",
                "turnover_value": "acml_tr_pbmn",
                "avg_turnover_value": "avrg_tr_pbmn",
                "turnover_value_turnover_pct": "tr_pbmn_tnrt",
                "listed_shares": "lstn_stcn",
            }.items():
                if item.get(key) is None:
                    item[key] = n(r.get(field))

    records: list[dict[str, Any]] = []
    for code, item in merged.items():
        meta = known.get(code)
        item["signals"] = "|".join(sorted(set(item["signals"])))
        item["known_in_universe"] = meta is not None
        item["registered_group"] = meta.get("group", "") if meta else ""
        item["registered_source"] = meta.get("source", "") if meta else ""
        item["classification_status"] = "registered_semiconductor" if meta else "pending_review"
        # 새 종목은 이름만 보고 반도체로 단정하지 않는다.
        item["eligible_for_model"] = bool(meta)
        records.append(item)

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(
            ["known_in_universe", "best_rank", "turnover_value"],
            ascending=[True, True, False],
            na_position="last",
        ).reset_index(drop=True)
    return df, errors


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["1540", "close", "manual"], default="manual")
    p.add_argument("--universe", default="universe.csv")
    p.add_argument("--config", default="scanner_config.json")
    args = p.parse_args()

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        print("ERROR: KIS_APP_KEY / KIS_APP_SECRET are required", file=sys.stderr)
        return 2

    u = load_universe(args.universe)
    cfg = load_config(args.config)
    client = KisClient(app_key, app_secret)
    client.auth()

    today = datetime.now(KST).strftime("%Y%m%d")
    probe_code = str(u.iloc[0]["code"])
    market_date = latest_market_date(client, probe_code)
    time.sleep(SLEEP_SEC)

    if args.mode in {"1540", "close"} and market_date != today:
        print(f"SKIP discovery: KRX appears closed. latest={market_date}, today={today}")
        return 0

    df, errors = discover(client, u, cfg)
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    if df.empty:
        df = pd.DataFrame(
            columns=[
                "code",
                "name",
                "signals",
                "best_rank",
                "market_cap_est_won",
                "known_in_universe",
                "classification_status",
                "eligible_for_model",
            ]
        )

    review = df[df["classification_status"].eq("pending_review")].copy()

    save(df, out_dir / f"{market_date}_{args.mode}_market_discovery.csv")
    save(df, out_dir / f"latest_{args.mode}_market_discovery.csv")
    save(review, out_dir / f"{market_date}_{args.mode}_review_queue.csv")
    save(review, out_dir / f"latest_{args.mode}_review_queue.csv")

    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": args.mode,
        "market_date": market_date,
        "registered_universe_count": int(len(u)),
        "market_rank_candidate_count": int(len(df)),
        "pending_review_count": int(len(review)),
        "discovery_errors": errors,
        "method": [
            "KRX volume increase rank",
            "KRX turnover rank",
            "KRX trading value rank",
            "KRX trading-value turnover rank",
        ],
        "important_limit": (
            "This is market-wide anomaly discovery from KIS ranking endpoints, not an exhaustive "
            "classification of every KRX company. Unknown names are never auto-scored as semiconductor "
            "stocks; they go to the review queue for business/profitability classification."
        ),
    }
    text = json.dumps(status, ensure_ascii=False, indent=2)
    (out_dir / f"{market_date}_{args.mode}_discovery_status.json").write_text(text, encoding="utf-8")
    (out_dir / f"latest_{args.mode}_discovery_status.json").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
