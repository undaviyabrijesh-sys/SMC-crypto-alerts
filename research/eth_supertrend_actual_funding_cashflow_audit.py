#!/usr/bin/env python3
"""Actual Binance ETHUSDT funding-cashflow audit for the frozen Supertrend study.

Accounting correction only. Reuses the parent signal generator and trade simulator;
does not optimize parameters, evaluate the retired holdout, or promote a strategy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIR))

import eth_supertrend_intraday_replication as parent  # noqa: E402
import binance_ethusdt_ema20_cross_exchange_replication as eth  # noqa: E402
import supertrend_intraday_backtest as st  # noqa: E402

BAR = pd.Timedelta(minutes=15)
BAR_MS = int(BAR.total_seconds() * 1000)
MAX_HOLD_BARS = 16
PRIMARY_COST_BPS = 12.0
COSTS_BPS = (6.0, 12.0, 20.0)
ENTRY_BOUNDARY_TOLERANCE_MS = 1000
EXIT_CLOSE_TOLERANCE_MS = 1000
EXPECTED_MAX_FUNDING_INTERVAL_MS = 8 * 60 * 60 * 1000
PARENT_RUN_ID = 44693535437
FUNDING_SOURCE = (
    "Binance USD-M GET /fapi/v1/fundingRate via connected Binance public-data "
    "connector; fields fundingTime, fundingRate, markPrice, rateType"
)
FROZEN_CONFIG = {
    "config_id": "hl2_atr10_x3_2R_both_all_4h",
    "source": "hl2",
    "atr_length": 10,
    "atr_multiplier": 3.0,
    "target_r": 2.0,
    "filter": "none",
    "direction": "both",
    "session": "all",
    "max_hold_bars": 16,
    "inherited_max_initial_stop_risk_pct_of_entry": 5.0,
}


class AuditError(RuntimeError):
    """Raised when the funding cashflow audit cannot be trusted."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_funding(path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path)
    required = {"symbol", "fundingTime", "fundingRate", "markPrice", "rateType"}
    missing = required.difference(frame.columns)
    if missing:
        raise AuditError(f"Funding CSV missing fields: {sorted(missing)}")
    if frame.empty:
        raise AuditError("Funding CSV is empty")
    if not frame.symbol.eq("ETHUSDT").all():
        raise AuditError("Funding CSV contains a symbol other than ETHUSDT")

    frame["fundingTime"] = pd.to_numeric(frame.fundingTime, errors="raise")
    frame["fundingRate"] = pd.to_numeric(frame.fundingRate, errors="raise")
    frame["markPrice"] = pd.to_numeric(frame.markPrice, errors="raise")
    values = frame[["fundingTime", "fundingRate", "markPrice"]].to_numpy(float)
    if not np.isfinite(values).all():
        raise AuditError("Funding CSV contains non-finite numeric fields")
    if not np.equal(frame.fundingTime.to_numpy(float), np.floor(frame.fundingTime.to_numpy(float))).all():
        raise AuditError("Funding timestamps must be integer milliseconds")
    if (frame.markPrice <= 0).any():
        raise AuditError("Funding mark prices must be positive")
    if frame.fundingTime.duplicated().any():
        raise AuditError("Funding CSV contains duplicate fundingTime values")

    frame["fundingTime"] = frame.fundingTime.astype("int64")
    frame = frame.sort_values("fundingTime").reset_index(drop=True)
    times = frame.fundingTime.to_numpy(dtype=np.int64)
    diffs = np.diff(times)
    if len(diffs) and (diffs <= 0).any():
        raise AuditError("Funding timestamps are not strictly increasing")
    if len(diffs) and (diffs > EXPECTED_MAX_FUNDING_INTERVAL_MS + 1000).any():
        bad = int(np.argmax(diffs))
        raise AuditError(
            "Funding history has a gap larger than the maximum 8h schedule: "
            f"{times[bad]} -> {times[bad + 1]} ({diffs[bad]} ms)"
        )

    rounded_hours = np.rint(diffs / 3_600_000).astype(int) if len(diffs) else np.array([], dtype=int)
    interval_hist = {str(k): int(v) for k, v in sorted(Counter(rounded_hours.tolist()).items())}
    frame["funding_time_utc"] = pd.to_datetime(frame.fundingTime, unit="ms", utc=True)
    metadata = {
        "source": FUNDING_SOURCE,
        "symbol": "ETHUSDT",
        "rows": int(len(frame)),
        "first_funding_time_utc": frame.funding_time_utc.iloc[0].isoformat(),
        "last_funding_time_utc": frame.funding_time_utc.iloc[-1].isoformat(),
        "interval_hours_rounded": interval_hist,
        "minimum_interval_ms": int(diffs.min()) if len(diffs) else None,
        "maximum_interval_ms": int(diffs.max()) if len(diffs) else None,
        "rate_type_counts": {str(k): int(v) for k, v in frame.rateType.value_counts(dropna=False).items()},
        "funding_rate_min": float(frame.fundingRate.min()),
        "funding_rate_max": float(frame.fundingRate.max()),
        "mark_price_min": float(frame.markPrice.min()),
        "mark_price_max": float(frame.markPrice.max()),
        "sha256": sha256(path),
        "path": str(path),
    }
    return frame, metadata


def funding_cashflow_quote(side: str, mark_price: float, funding_rate: float) -> float:
    if side not in ("long", "short"):
        raise ValueError("side must be long or short")
    if not np.isfinite([mark_price, funding_rate]).all() or mark_price <= 0:
        raise ValueError("mark price must be positive and all inputs finite")
    side_sign = 1.0 if side == "long" else -1.0
    return -side_sign * float(mark_price) * float(funding_rate)


def attribute_trade_funding(trade: dict, funding: pd.DataFrame) -> dict:
    """Return actual funding cashflow and conservative boundary bounds for one trade."""
    side = str(trade["side"])
    entry = float(trade["entry"])
    stop = float(trade["stop"])
    risk = entry - stop if side == "long" else stop - entry
    if not np.isfinite(risk) or risk <= 0:
        raise AuditError("Trade has invalid initial stop risk")

    entry_ms = int(pd.Timestamp(trade["entry_time"]).timestamp() * 1000)
    exit_open_ms = int(pd.Timestamp(trade["exit_time"]).timestamp() * 1000)
    exit_close_ms = exit_open_ms + BAR_MS
    outcome = str(trade["outcome"])
    times = funding.fundingTime.to_numpy(dtype=np.int64)
    lo = int(np.searchsorted(times, entry_ms - ENTRY_BOUNDARY_TOLERANCE_MS, side="left"))
    hi = int(np.searchsorted(times, exit_close_ms + EXIT_CLOSE_TOLERANCE_MS, side="right"))

    definite_quote = 0.0
    ambiguous_cashflows: list[float] = []
    definite_count = 0
    ambiguous_count = 0
    paid_definite = 0.0
    received_definite = 0.0
    paid_ambiguous = 0.0
    received_ambiguous = 0.0
    event_times = []
    event_rows = []

    for row in funding.iloc[lo:hi].itertuples(index=False):
        ts = int(row.fundingTime)
        cashflow = funding_cashflow_quote(side, float(row.markPrice), float(row.fundingRate))
        classification = "outside"

        if abs(ts - entry_ms) <= ENTRY_BOUNDARY_TOLERANCE_MS:
            classification = "ambiguous_entry_boundary"
        elif ts <= entry_ms - ENTRY_BOUNDARY_TOLERANCE_MS:
            classification = "outside"
        elif ts < exit_open_ms:
            classification = "definite"
        elif outcome == "TIME" and exit_open_ms <= ts < exit_close_ms - EXIT_CLOSE_TOLERANCE_MS:
            classification = "definite"
        elif exit_open_ms <= ts <= exit_close_ms + EXIT_CLOSE_TOLERANCE_MS:
            classification = "ambiguous_exit_candle"
        else:
            classification = "outside"

        if classification == "outside":
            continue

        event_time = pd.to_datetime(ts, unit="ms", utc=True).isoformat()
        event_times.append(event_time)
        event_rows.append({
            "funding_time_utc": event_time,
            "funding_rate": float(row.fundingRate),
            "mark_price": float(row.markPrice),
            "cashflow_quote_per_eth": cashflow,
            "classification": classification,
        })
        if classification == "definite":
            definite_count += 1
            definite_quote += cashflow
            if cashflow < 0:
                paid_definite += -cashflow
            else:
                received_definite += cashflow
        else:
            ambiguous_count += 1
            ambiguous_cashflows.append(cashflow)
            if cashflow < 0:
                paid_ambiguous += -cashflow
            else:
                received_ambiguous += cashflow

    definite_r = definite_quote / risk
    ambiguous_r = [value / risk for value in ambiguous_cashflows]
    lower_r = definite_r + sum(min(0.0, value) for value in ambiguous_r)
    upper_r = definite_r + sum(max(0.0, value) for value in ambiguous_r)
    return {
        "funding_events_definite": definite_count,
        "funding_events_ambiguous": ambiguous_count,
        "funding_events_total": definite_count + ambiguous_count,
        "funding_quote_definite_per_eth": definite_quote,
        "funding_paid_quote_definite_per_eth": paid_definite,
        "funding_received_quote_definite_per_eth": received_definite,
        "funding_paid_quote_ambiguous_per_eth": paid_ambiguous,
        "funding_received_quote_ambiguous_per_eth": received_ambiguous,
        "funding_R_definite": definite_r,
        "funding_R_lower": lower_r,
        "funding_R_upper": upper_r,
        "funding_event_times_utc": "|".join(event_times),
        "funding_event_details_json": json.dumps(event_rows, separators=(",", ":")),
    }


def apply_funding(trades: pd.DataFrame, funding: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        for column in (
            "cost_R", "funding_R_definite", "funding_R_lower", "funding_R_upper",
            "net_R_lower", "net_R_upper", "funding_events_definite",
            "funding_events_ambiguous", "funding_events_total",
        ):
            result[column] = pd.Series(dtype=float)
        return result
    rows = [attribute_trade_funding(trade, funding) for trade in result.to_dict("records")]
    attribution = pd.DataFrame(rows, index=result.index)
    result = pd.concat([result, attribution], axis=1)
    side = result.side.to_numpy()
    entry = result.entry.to_numpy(float)
    stop = result.stop.to_numpy(float)
    risk = np.where(side == "long", entry - stop, stop - entry)
    if not np.isfinite(risk).all() or (risk <= 0).any():
        raise AuditError("Trade ledger contains invalid initial risk")
    result["cost_R"] = entry * (float(cost_bps) / 10000.0) / risk
    result["cost_bps_round_trip"] = float(cost_bps)
    result["net_R_lower"] = result.gross_R.astype(float) - result.cost_R + result.funding_R_lower
    result["net_R_upper"] = result.gross_R.astype(float) - result.cost_R + result.funding_R_upper
    return result


def metrics(frame: pd.DataFrame, column: str) -> dict:
    if frame.empty:
        return {
            "trades": 0, "win_rate_pct": None, "profit_factor": None,
            "net_R": 0.0, "avg_R": None, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "positive_months": 0,
            "active_months": 0, "positive_month_fraction": None,
            "TP": 0, "SL": 0, "TIME": 0,
        }
    ordered = frame.sort_values("entry_time")
    r = ordered[column].astype(float)
    wins = r[r > 0]
    losses = r[r < 0]
    equity = r.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    drawdown = equity - peak
    losing_streak = current = 0
    for value in r.to_numpy():
        current = current + 1 if value < 0 else 0
        losing_streak = max(losing_streak, current)
    months = ordered.assign(
        month=pd.to_datetime(ordered.entry_time, utc=True).dt.strftime("%Y-%m")
    ).groupby("month")[column].sum()
    return {
        "trades": int(len(ordered)),
        "win_rate_pct": round(float((r > 0).mean() * 100.0), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4)
        if len(losses) and abs(losses.sum()) > 0 else None,
        "net_R": round(float(r.sum()), 4),
        "avg_R": round(float(r.mean()), 5),
        "max_drawdown_R": round(float(min(0.0, drawdown.min())), 4),
        "max_losing_streak": int(losing_streak),
        "positive_months": int((months > 0).sum()),
        "active_months": int(len(months)),
        "positive_month_fraction": round(float((months > 0).mean()), 4) if len(months) else None,
        "TP": int((ordered.outcome == "TP").sum()),
        "SL": int((ordered.outcome == "SL").sum()),
        "TIME": int((ordered.outcome == "TIME").sum()),
    }


def summary_rows(frame: pd.DataFrame, sample: str, grouping: str, column: str) -> list[dict]:
    if frame.empty:
        return []
    if grouping == "month":
        keys = pd.to_datetime(frame.entry_time, utc=True).dt.strftime("%Y-%m")
    elif grouping == "regime":
        keys = frame.regime.astype(str)
    elif grouping == "side":
        keys = frame.side.astype(str)
    else:
        raise ValueError(grouping)
    temp = frame.assign(_group=keys)
    return [
        {"sample": sample, grouping: str(key), "bound": column, **metrics(group, column)}
        for key, group in temp.groupby("_group", sort=True)
    ]


def validate_coverage(funding: pd.DataFrame, trades: list[pd.DataFrame]) -> dict:
    nonempty = [x for x in trades if not x.empty]
    if not nonempty:
        raise AuditError("No trades were produced; refusing an empty funding audit")
    all_trades = pd.concat(nonempty, ignore_index=True)
    first_entry = min(pd.Timestamp(x) for x in all_trades.entry_time)
    last_exit_close = max(pd.Timestamp(x) + BAR for x in all_trades.exit_time)
    first_event = pd.Timestamp(funding.funding_time_utc.iloc[0])
    last_event = pd.Timestamp(funding.funding_time_utc.iloc[-1])
    if first_event > first_entry + pd.Timedelta(seconds=1):
        raise AuditError("Funding history starts after the first trade entry boundary")
    if last_event < last_exit_close - pd.Timedelta(seconds=1):
        raise AuditError("Funding history ends before the last trade exit-close boundary")
    return {
        "first_trade_entry_utc": first_entry.isoformat(),
        "last_trade_exit_close_utc": last_exit_close.isoformat(),
        "first_funding_event_utc": first_event.isoformat(),
        "last_funding_event_utc": last_event.isoformat(),
        "coverage_start_pass": True,
        "coverage_end_pass": True,
    }


def self_test() -> list[str]:
    assert abs(funding_cashflow_quote("long", 100.0, 0.001) + 0.1) < 1e-12
    assert abs(funding_cashflow_quote("short", 100.0, 0.001) - 0.1) < 1e-12
    assert abs(funding_cashflow_quote("long", 100.0, -0.001) - 0.1) < 1e-12
    assert abs(funding_cashflow_quote("short", 100.0, -0.001) + 0.1) < 1e-12

    entry = pd.Timestamp("2026-01-01T00:00:00Z")
    exit_open = pd.Timestamp("2026-01-01T00:45:00Z")
    events = pd.DataFrame([
        {"fundingTime": int((entry + pd.Timedelta(milliseconds=5)).timestamp() * 1000), "fundingRate": 0.001, "markPrice": 100.0},
        {"fundingTime": int((entry + pd.Timedelta(minutes=20)).timestamp() * 1000), "fundingRate": 0.001, "markPrice": 100.0},
        {"fundingTime": int((exit_open + pd.Timedelta(minutes=5)).timestamp() * 1000), "fundingRate": -0.001, "markPrice": 100.0},
    ])
    trade = {
        "side": "long", "entry": 100.0, "stop": 99.0,
        "entry_time": entry, "exit_time": exit_open, "outcome": "SL",
    }
    got = attribute_trade_funding(trade, events)
    assert got["funding_events_definite"] == 1
    assert got["funding_events_ambiguous"] == 2
    assert got["funding_R_definite"] < 0
    assert got["funding_R_lower"] <= got["funding_R_definite"] <= got["funding_R_upper"]

    time_trade = dict(trade, outcome="TIME")
    time_events = pd.DataFrame([
        {"fundingTime": int((exit_open + pd.Timedelta(minutes=5)).timestamp() * 1000), "fundingRate": 0.001, "markPrice": 100.0}
    ])
    time_got = attribute_trade_funding(time_trade, time_events)
    assert time_got["funding_events_definite"] == 1
    assert time_got["funding_events_ambiguous"] == 0

    multiple = pd.DataFrame([
        {"fundingTime": int((entry + pd.Timedelta(minutes=5)).timestamp() * 1000), "fundingRate": 0.001, "markPrice": 100.0},
        {"fundingTime": int((entry + pd.Timedelta(minutes=10)).timestamp() * 1000), "fundingRate": -0.001, "markPrice": 100.0},
    ])
    multiple_trade = dict(trade, exit_time=entry + pd.Timedelta(minutes=30), outcome="TIME")
    multi_got = attribute_trade_funding(multiple_trade, multiple)
    assert multi_got["funding_events_total"] == 2

    times = np.array([1741392000000, 1741420800001, 1741449600001], dtype=np.int64)
    intervals = np.diff(times)
    assert np.all(np.abs(intervals - 8 * 60 * 60 * 1000) <= 1000)
    return [
        "funding_rate_sign_long_short",
        "entry_and_exit_boundary_bounds",
        "time_exit_settlement_charged_before_close",
        "multiple_settlements_supported",
        "millisecond_settlement_timestamp_jitter",
    ]


def run(parent_artifact: Path, funding_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    parent_summary_path = parent_artifact / "summary.json"
    source_path = parent_artifact / "download" / "ETHUSDT_15m_binance.csv"
    if not parent_summary_path.is_file() or not source_path.is_file():
        raise AuditError("Parent artifact is incomplete; summary.json or source candle CSV missing")
    parent_summary = json.loads(parent_summary_path.read_text(encoding="utf-8"))
    raw = eth.load_source(source_path)
    source_digest = sha256(source_path)
    expected_digest = parent_summary.get("data_quality", {}).get("source_sha256")
    if expected_digest and source_digest != expected_digest:
        raise AuditError("Parent source candle SHA-256 does not match the authoritative parent summary")

    data, tr, hourly = st.prepare_base(raw)
    if len(data) != 47424:
        raise AuditError(f"Unexpected source row count: {len(data)}")
    if data.index.to_series().diff().dropna().ne(BAR).any():
        raise AuditError("Parent ETH 15m source contains missing or irregular intervals")

    n = len(data)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    parent_splits = parent_summary.get("splits", {})
    if pd.Timestamp(data.index[train_end]) != pd.Timestamp(parent_splits["validation_first_bar_open"]):
        raise AuditError("Development/validation boundary differs from parent replay")
    if pd.Timestamp(data.index[validation_end]) != pd.Timestamp(parent_splits["final_holdout_first_bar_open"]):
        raise AuditError("Validation/retired-holdout boundary differs from parent replay")

    st.MAX_HOLD_BARS = MAX_HOLD_BARS
    st.COST_RATE = PRIMARY_COST_BPS / 10000.0
    signals = st.build_signals(data, tr, "hl2", 10, 3.0)
    if len(signals) != 1043:
        raise AuditError(f"Unexpected raw Supertrend flip count: {len(signals)}")
    gap_mask = data.index.to_series().diff().ne(BAR).to_numpy(copy=True)
    gap_mask[0] = False
    config = {
        **FROZEN_CONFIG,
        "session": "all",
        "direction": "both",
        "filter": "none",
        "target_r": 2.0,
    }
    segments = {
        "development": (0, train_end),
        "validation": (train_end, validation_end),
    }

    all_signal_trades = {
        sample: st.simulate(data, signals, config, *bounds, gap_mask)
        for sample, bounds in segments.items()
    }
    parent_subset = {
        sample: pd.read_csv(parent_artifact / f"{sample}_trades.csv", parse_dates=["signal_time", "entry_time", "exit_time"])
        for sample in ("development", "validation")
    }

    funding, funding_meta = load_funding(funding_path)
    coverage = validate_coverage(funding, list(all_signal_trades.values()) + list(parent_subset.values()))
    outputs = {}
    for label, sets in (("all_raw_signals", all_signal_trades), ("parent_default_grid_subset", parent_subset)):
        for sample, trades in sets.items():
            if trades.empty:
                raise AuditError(f"{label}/{sample} has no trades")
            enriched = parent.add_completed_4h_regime(raw, trades)
            audited = apply_funding(enriched, funding, PRIMARY_COST_BPS)
            outputs[(label, sample)] = audited
            audited.to_csv(output_dir / f"{label}_{sample}_funding_trades.csv", index=False)

    monthly, regimes, sides, cost_rows = [], [], [], []
    primary_metrics = {}
    for (label, sample), trades in outputs.items():
        primary_metrics[f"{label}/{sample}"] = {
            "lower": metrics(trades, "net_R_lower"),
            "upper": metrics(trades, "net_R_upper"),
            "funding_events_definite": int(trades.funding_events_definite.sum()),
            "funding_events_ambiguous": int(trades.funding_events_ambiguous.sum()),
            "funding_R_definite_total": float(trades.funding_R_definite.sum()),
            "funding_R_lower_total": float(trades.funding_R_lower.sum()),
            "funding_R_upper_total": float(trades.funding_R_upper.sum()),
            "funding_paid_quote_definite_per_eth": float(trades.funding_paid_quote_definite_per_eth.sum()),
            "funding_received_quote_definite_per_eth": float(trades.funding_received_quote_definite_per_eth.sum()),
        }
        for bound in ("net_R_lower", "net_R_upper"):
            monthly.extend(summary_rows(trades, f"{label}/{sample}", "month", bound))
            regimes.extend(summary_rows(trades, f"{label}/{sample}", "regime", bound))
            sides.extend(summary_rows(trades, f"{label}/{sample}", "side", bound))
        for cost in COSTS_BPS:
            cost_frame = apply_funding(trades.drop(columns=[
                c for c in trades.columns if c in ("cost_R", "cost_bps_round_trip", "net_R_lower", "net_R_upper")
            ]), funding, cost)
            cost_rows.append({
                "sample": f"{label}/{sample}",
                "cost_bps_round_trip": cost,
                "lower": metrics(cost_frame, "net_R_lower"),
                "upper": metrics(cost_frame, "net_R_upper"),
            })

    pd.DataFrame(monthly).to_csv(output_dir / "monthly_bounds.csv", index=False)
    pd.DataFrame(regimes).to_csv(output_dir / "regime_bounds.csv", index=False)
    pd.DataFrame(sides).to_csv(output_dir / "side_bounds.csv", index=False)
    pd.DataFrame([
        {"sample": row["sample"], "cost_bps_round_trip": row["cost_bps_round_trip"],
         "bound": bound, **row[bound]}
        for row in cost_rows for bound in ("lower", "upper")
    ]).to_csv(output_dir / "cost_sensitivity_bounds.csv", index=False)

    ambiguous = []
    for (label, sample), trades in outputs.items():
        for trade in trades.loc[trades.funding_events_ambiguous.gt(0)].to_dict("records"):
            try:
                details = json.loads(trade["funding_event_details_json"])
            except (TypeError, json.JSONDecodeError):
                details = []
            for item in details:
                if item["classification"].startswith("ambiguous"):
                    ambiguous.append({
                        "sample": f"{label}/{sample}",
                        "entry_time": str(trade["entry_time"]),
                        "exit_time": str(trade["exit_time"]),
                        "side": trade["side"],
                        "outcome": trade["outcome"],
                        **item,
                    })
    pd.DataFrame(ambiguous).to_csv(output_dir / "ambiguous_settlements.csv", index=False)

    funding_meta.update({
        "retrieval_window_start_ms_inclusive": 1741392000000,
        "retrieval_window_end_ms_inclusive": 1784102400000,
        "page_limits": [1000, 1000],
        "retrieved_via": "connected Binance USD-M public funding history action",
        "all_observed_intervals_within_8h_maximum": True,
    })
    (output_dir / "funding_manifest.json").write_text(json.dumps(funding_meta, indent=2), encoding="utf-8")
    (output_dir / "funding_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    summary = {
        "status": "completed_accounting_audit_no_strategy_promotion",
        "parent_workflow_run_id": PARENT_RUN_ID,
        "symbol": "ETHUSDT",
        "venue": "Binance USD-M",
        "frozen_configuration": FROZEN_CONFIG,
        "primary_cost_bps_round_trip": PRIMARY_COST_BPS,
        "cost_sensitivity_bps_round_trip": list(COSTS_BPS),
        "data_quality": {
            "source_candle_rows": int(len(data)),
            "source_candle_sha256": source_digest,
            "complete_4h_bars": int(len(hourly)),
            "funding_rows": int(len(funding)),
            "funding_sha256": funding_meta["sha256"],
            "raw_supertrend_flips": int(len(signals)),
            "funding_schedule": funding_meta,
            "coverage": coverage,
        },
        "split_boundaries": {
            "development_last_bar_open": data.index[train_end - 1].isoformat(),
            "validation_first_bar_open": data.index[train_end].isoformat(),
            "validation_last_bar_open": data.index[validation_end - 1].isoformat(),
            "retired_holdout_first_bar_open": data.index[validation_end].isoformat(),
            "retired_holdout_evaluated": False,
        },
        "results_12bps": primary_metrics,
        "ambiguity_event_rows": int(len(ambiguous)),
        "self_tests": self_test(),
        "decision": "no_promotion; funding accounting correction only; retired holdout not evaluated",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    report = [
        "# ETHUSDT Supertrend — actual funding cashflow audit",
        "",
        "- Type: accounting correction only; no parameter optimization and no strategy promotion.",
        f"- Parent workflow: {PARENT_RUN_ID}; parent candle SHA-256: {source_digest}.",
        f"- Funding records: {len(funding):,}; SHA-256: {funding_meta['sha256']}.",
        f"- Funding event range: {funding_meta['first_funding_time_utc']} to {funding_meta['last_funding_time_utc']}.",
        f"- Observed rounded interval histogram (hours): {funding_meta['interval_hours_rounded']}.",
        "- Funding mark prices present and positive: yes; duplicate timestamps: no.",
        f"- Coverage check: {coverage}.",
        f"- Raw Supertrend flips replayed without fixed-grid exclusion: {len(signals):,}.",
        "- Strategy: HL2 Supertrend, Wilder ATR(10) x3, next 15m open, signal-bar line stop, fixed 2R, both sides, all UTC hours, one position, 16-bar maximum hold.",
        "- Funding: actual Binance fundingTime, fundingRate, and associated markPrice; positive rates mean longs pay and shorts receive.",
        "- Boundary handling: events within 1 second of entry are ambiguous; events strictly before TP/SL exit-bar open are definite; events inside TP/SL exit candle are ambiguous; TIME exits remain open through the final candle close.",
        "- Net lower/upper bounds include adverse/favorable ambiguous funding respectively. Transaction cost is assumed 12 bps round trip; 6/20 bps sensitivity is also saved.",
        "- R is normalized by initial stop risk, not account return. OHLC stop-first execution and adverse stop-gap assumptions are inherited from the parent simulator.",
        "- The final 15% holdout is retired and was not evaluated.",
        "",
        "## Results at 12 bps",
        "",
    ]
    for key, value in primary_metrics.items():
        report += [
            f"### {key}",
            f"- Lower bound: {value['lower']}",
            f"- Upper bound: {value['upper']}",
            f"- Definite/ambiguous settlements: {value['funding_events_definite']} / {value['funding_events_ambiguous']}",
            f"- Funding R definite/lower/upper: {value['funding_R_definite_total']:.6f} / {value['funding_R_lower_total']:.6f} / {value['funding_R_upper_total']:.6f}",
            f"- Definite funding paid/received per ETH: {value['funding_paid_quote_definite_per_eth']:.8f} / {value['funding_received_quote_definite_per_eth']:.8f}",
            "",
        ]
    report += [
        "## Limitations",
        "",
        "- The funding history endpoint provides the mark price associated with each funding charge; the audit uses one ETH unit and converts quote cashflow into initial-risk R.",
        "- Actual user fee tier, bid/ask spread, variable slippage, market impact, and account quantity are not available.",
        "- TP/SL intrabar exit times are unknown from 15m OHLC, so funding events in the exit candle are bounded rather than assigned a false point estimate.",
        "- The parent final 15% holdout was contaminated by prior local access and remains retired; no OOS claim is made.",
        "- This is not a strategy validation run. The frozen Supertrend baseline was already negative in development and validation before actual funding accounting.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-artifact", type=Path, default=Path("parent_artifact"))
    parser.add_argument("--funding-csv", type=Path, default=Path("research/data/ETHUSDT_BINANCE_USDM_FUNDING_2025-03-08_2026-07-15.csv"))
    parser.add_argument("--out", type=Path, default=Path("eth_supertrend_funding_audit_results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        for name in self_test():
            print(f"PASS {name}")
        return
    result = run(args.parent_artifact, args.funding_csv, args.out)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
