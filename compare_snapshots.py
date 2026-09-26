from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from kis_collect import KST


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="")
    args = p.parse_args()

    out_dir = Path("data")
    close_path = out_dir / "latest_close.csv"
    intraday_path = out_dir / "latest_1540.csv"

    status = {
        "snapshot_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "available": False,
        "reason": "",
    }

    if not close_path.exists() or not intraday_path.exists():
        status["reason"] = "1540 or close snapshot missing"
        (out_dir / "latest_close_vs_1540_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(status["reason"])
        return 0

    a = pd.read_csv(intraday_path, dtype={"code": str})
    b = pd.read_csv(close_path, dtype={"code": str})
    a["code"] = a["code"].str.zfill(6)
    b["code"] = b["code"].str.zfill(6)

    a_date = str(a["market_date"].iloc[0]) if len(a) else ""
    b_date = str(b["market_date"].iloc[0]) if len(b) else ""
    if a_date != b_date:
        status["reason"] = f"snapshot date mismatch: 1540={a_date}, close={b_date}"
        (out_dir / "latest_close_vs_1540_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(status["reason"])
        return 0

    keep = [
        "code", "name", "group", "price", "change_pct", "volume", "turnover_value_raw",
        "close_position_pct", "upper_wick_pct", "volume_vs_20d_x", "turnover_vs_20d_x",
        "foreign_today_qty", "institution_today_qty", "program_today_qty"
    ]
    keep_a = [x for x in keep if x in a.columns]
    keep_b = [x for x in keep if x in b.columns]
    aa = a[keep_a].copy().add_suffix("_1540").rename(columns={"code_1540": "code"})
    bb = b[keep_b].copy().add_suffix("_close").rename(columns={"code_close": "code"})
    m = aa.merge(bb, on="code", how="outer")

    def diff(name: str):
        l, r = f"{name}_1540", f"{name}_close"
        if l in m.columns and r in m.columns:
            m[f"{name}_delta"] = num(m[r]) - num(m[l])

    for col in [
        "price", "change_pct", "volume", "turnover_value_raw", "close_position_pct",
        "upper_wick_pct", "volume_vs_20d_x", "turnover_vs_20d_x",
        "foreign_today_qty", "institution_today_qty", "program_today_qty"
    ]:
        diff(col)

    if "price_1540" in m.columns and "price_close" in m.columns:
        p1540, pcl = num(m["price_1540"]), num(m["price_close"])
        m["price_hold_pct"] = (pcl / p1540 - 1.0) * 100.0
    if "volume_1540" in m.columns and "volume_close" in m.columns:
        v1, v2 = num(m["volume_1540"]), num(m["volume_close"])
        m["post1540_volume_inflow_pct"] = (v2 / v1 - 1.0) * 100.0
    if "turnover_value_raw_1540" in m.columns and "turnover_value_raw_close" in m.columns:
        t1, t2 = num(m["turnover_value_raw_1540"]), num(m["turnover_value_raw_close"])
        m["post1540_turnover_inflow_pct"] = (t2 / t1 - 1.0) * 100.0

    # 판단용 보조 플래그. 모델 점수를 대신하지 않는다.
    if "price_hold_pct" in m.columns and "close_position_pct_close" in m.columns:
        hold = num(m["price_hold_pct"])
        close_pos = num(m["close_position_pct_close"])
        m["signal_1540_to_close"] = "neutral"
        m.loc[(hold >= -1.0) & (close_pos >= 70), "signal_1540_to_close"] = "maintained"
        m.loc[(hold <= -3.0) | (close_pos <= 35), "signal_1540_to_close"] = "failed"

    market_date = b_date
    m.to_csv(out_dir / f"{market_date}_close_vs_1540.csv", index=False, encoding="utf-8-sig")
    m.to_csv(out_dir / "latest_close_vs_1540.csv", index=False, encoding="utf-8-sig")

    status.update({
        "available": True,
        "reason": "ok",
        "market_date": market_date,
        "row_count": int(len(m)),
        "note": "보조 비교 데이터이며 A/B 점수를 자동 결정하지 않음",
    })
    text = json.dumps(status, ensure_ascii=False, indent=2)
    (out_dir / f"{market_date}_close_vs_1540_status.json").write_text(text, encoding="utf-8")
    (out_dir / "latest_close_vs_1540_status.json").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
