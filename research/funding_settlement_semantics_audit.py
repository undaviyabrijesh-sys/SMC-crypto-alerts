#!/usr/bin/env python3
"""Audit Delta BTC/ETH historical funding-rate series and funding-rule regimes.

This is a data-semantics audit, not a funding PnL model. It deliberately does
not apply funding to trades until the pre/post-2025-09-08 cashflow mechanics
and rate-to-settlement timestamp convention are independently reconciled.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import requests
import numpy as np
import pandas as pd

BASE_URL = "https://api.india.delta.exchange"
ASSETS = ("BTC", "ETH")
TRANSITION_UTC = pd.Timestamp("2025-09-08T12:00:00Z")  # 17:30 IST
SETTLEMENT_HOURS_UTC = (0, 8, 16)
EXPECTED_STEP = pd.Timedelta(hours=1)


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_settlement_grid(ts: pd.Timestamp) -> bool:
    ts = pd.Timestamp(ts)
    return ts.minute == 0 and ts.second == 0 and ts.hour in SETTLEMENT_HOURS_UTC


def load_funding(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    if "timestamp" not in d:
        raise AuditError(f"{path}: missing timestamp")
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True, errors="raise")
    if d.timestamp.duplicated().any():
        raise AuditError(f"{path}: duplicate timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    required = ("open", "high", "low", "close", "volume")
    if not set(required).issubset(d.columns):
        raise AuditError(f"{path}: missing funding OHLCV columns")
    for col in required:
        d[col] = pd.to_numeric(d[col], errors="raise")
        if not np.isfinite(d[col].to_numpy(float)).all():
            raise AuditError(f"{path}: non-finite {col}")
    if (d.volume < 0).any():
        raise AuditError(f"{path}: negative volume")
    if (d.high < d[["open", "close", "low"]].max(axis=1)).any():
        raise AuditError(f"{path}: invalid high")
    if (d.low > d[["open", "close", "high"]].min(axis=1)).any():
        raise AuditError(f"{path}: invalid low")
    return d


def window_summary(d: pd.DataFrame, label: str) -> dict:
    if d.empty:
        return {"rows": 0, "status": "empty"}
    delta = d.index.to_series().diff().dropna()
    change = d.close.ne(d.close.shift(1))
    changes = d.loc[change].copy()
    if not changes.empty:
        changes = changes.iloc[1:]  # first observation is not a transition
    transition_changes = changes.index == TRANSITION_UTC
    regular_changes = changes.loc[~transition_changes]
    off_grid = [ts.isoformat() for ts in regular_changes.index if not is_settlement_grid(ts)]

    blocks = d[["close"]].copy()
    blocks["block"] = blocks.index.floor("8h")
    block_stats = blocks.groupby("block").close.agg(
        rows="count", unique_rates="nunique", first_rate="first", last_rate="last"
    )
    full = block_stats[block_stats.rows == 8]
    flat = full[full.unique_rates == 1]

    hour_counts = {}
    if not regular_changes.empty:
        hour_counts = {
            f"{int(hour):02d}:{int(minute):02d}": int(n)
            for (hour, minute), n in regular_changes.groupby(
                [regular_changes.index.hour, regular_changes.index.minute]
            ).size().items()
        }
    ohlc_identical = {
        col: round(float((d[col] == d.close).mean()), 6)
        for col in ("open", "high", "low")
    }
    return {
        "label": label,
        "rows": int(len(d)),
        "start_utc": d.index.min().isoformat(),
        "end_utc": d.index.max().isoformat(),
        "missing_hour_intervals": int((delta > EXPECTED_STEP * 1.5).sum()),
        "irregular_hour_intervals": int((delta != EXPECTED_STEP).sum()),
        "rate_change_count_excluding_first": int(len(changes)),
        "transition_timestamp_change_count": int(transition_changes.sum()),
        "regular_rate_changes_by_utc_hour": hour_counts,
        "off_grid_rate_change_count_excluding_transition": int(len(off_grid)),
        "off_grid_rate_change_examples_utc": off_grid[:20],
        "full_8h_blocks": int(len(full)),
        "flat_full_8h_blocks": int(len(flat)),
        "flat_full_8h_block_fraction": round(float(len(flat) / len(full)), 6) if len(full) else None,
        "funding_ohlc_equal_close_fraction": ohlc_identical,
        "rate_value_min": round(float(d.close.min()), 10),
        "rate_value_max": round(float(d.close.max()), 10),
        "rate_value_median": round(float(d.close.median()), 10),
        "rate_value_median_abs": round(float(d.close.abs().median()), 10),
    }


def fetch_product_specs(symbol: str) -> dict:
    url = f"{BASE_URL}/v2/products/{symbol}USD"
    try:
        r = requests.get(url, headers={"Accept": "application/json",
            "User-Agent": "SaltyQuantFundingSemanticsAudit/1.0"}, timeout=20)
        r.raise_for_status()
        payload = r.json()
        if payload.get("success") is not True:
            return {"status": "unavailable", "error": "unsuccessful product response"}
        p = payload.get("result") or {}
        spec = p.get("product_specs") or {}
        return {
            "status": "retrieved",
            "symbol": p.get("symbol"),
            "contract_type": p.get("contract_type"),
            "rate_exchange_interval_seconds": spec.get("rate_exchange_interval"),
            "funding_clamp_value_raw": spec.get("funding_clamp_value"),
            "contract_value": p.get("contract_value"),
            "contract_unit_currency": p.get("contract_unit_currency"),
            "settling_asset": (p.get("settling_asset") or {}).get("symbol"),
            "funding_method": p.get("funding_method"),
        }
    except (requests.RequestException, ValueError) as exc:
        return {"status": "unavailable", "error": str(exc)[:300]}


def audit_asset(asset: str, path: Path) -> dict:
    d = load_funding(path)
    pre = d[d.index < TRANSITION_UTC]
    post = d[d.index >= TRANSITION_UTC]
    return {
        "asset": asset,
        "csv_sha256": sha256(path),
        "overall": window_summary(d, "all"),
        "pre_transition": window_summary(pre, "before_2025-09-08T12:00:00Z"),
        "post_transition": window_summary(post, "from_2025-09-08T12:00:00Z"),
        "current_product_specs": fetch_product_specs(asset),
    }


def self_test():
    idx = pd.date_range("2026-01-01T00:00:00Z", periods=24, freq="1h")
    rates = np.repeat([0.01, -0.02, 0.005], 8)
    d = pd.DataFrame({"open": rates, "high": rates, "low": rates,
        "close": rates, "volume": 0.0}, index=idx)
    s = window_summary(d, "synthetic")
    assert s["full_8h_blocks"] == 3
    assert s["flat_full_8h_blocks"] == 3
    assert s["off_grid_rate_change_count_excluding_transition"] == 0
    assert is_settlement_grid(pd.Timestamp("2026-01-01T00:00:00Z"))
    assert is_settlement_grid(pd.Timestamp("2026-01-01T08:00:00Z"))
    assert is_settlement_grid(pd.Timestamp("2026-01-01T16:00:00Z"))
    assert not is_settlement_grid(pd.Timestamp("2026-01-01T09:00:00Z"))
    assert TRANSITION_UTC == pd.Timestamp("2025-09-08T12:00:00Z")
    print("PASS flat_8h_rate_blocks")
    print("PASS 00_08_16_utc_settlement_grid")
    print("PASS off_grid_change_detection")
    print("PASS mechanism_transition_timestamp")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("historical_data/derivatives"))
    p.add_argument("--output-dir", type=Path, default=Path("research/results/funding_semantics"))
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    reports = {}
    for asset in ASSETS:
        path = a.data_dir / f"{asset}_funding_1h.csv"
        if not path.is_file():
            raise AuditError(f"missing required funding dataset: {path}")
        reports[asset] = audit_asset(asset, path)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "completed",
        "source": "Delta Exchange India public FUNDING:<symbol> 1h historical candles",
        "mechanism_transition_utc": TRANSITION_UTC.isoformat(),
        "candidate_current_settlement_grid_utc": ["00:00", "08:00", "16:00"],
        "assets": reports,
        "interpretation": [
            "A flat 1h funding-rate series within each 8h block supports an 8h rate-update cadence; it does not by itself prove when cashflow is exchanged.",
            "Delta's current product metadata and public funding_rate websocket expose rate_exchange_interval/fi and next_funding_realization; reconcile these fields with historical candles before applying a rate to a specific settlement.",
            "The published mechanism changed at 2025-09-08 17:30 IST (12:00 UTC): before that, funding was exchanged every minute while the rate was computed every 8h; after that, funding is exchanged at 8h snapshots.",
            "The public documentation does not fully specify the historical minute-level cashflow normalization for the pre-transition regime. Do not apply the post-transition 8h snapshot model to pre-transition trades.",
            "Historical OHLC candles do not explicitly declare whether rate values are decimal fractions or percentage points. Values around 0.01 are consistent with the guide's 0.01% example, but the unit and rate-to-settlement timestamp mapping require a direct reconciliation before PnL use.",
            "No funding payment is calculated by this audit; no strategy performance is adjusted."
        ],
        "funding_cashflow_model_status": "not_implemented_pending_rate_unit_and_pre_transition_cashflow_reconciliation"
    }
    (a.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
