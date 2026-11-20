#!/usr/bin/env python3
"""Frozen ETHUSDT 15m Supertrend intraday cross-asset replication.

Reuses the repository BTC Supertrend indicator/trade simulator and the verified
Binance ETH archive downloader. One fixed baseline; no parameter grid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIR))

import binance_ethusdt_ema20_cross_exchange_replication as eth  # noqa: E402
import supertrend_intraday_backtest as st  # noqa: E402

BAR = pd.Timedelta(minutes=15)
ATR_SOURCE = "hl2"
ATR_LENGTH = 10
ATR_MULTIPLIER = 3.0
TARGET_R = 2.0
MAX_HOLD_BARS = 16  # 4 hours
PRIMARY_COST_BPS = 12.0
COSTS_BPS = (6.0, 12.0, 20.0)
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MIN_PF = 1.05
MIN_POSITIVE_MONTH_FRACTION = 0.50
OOS_EVALUATION_ENABLED = False  # reserved 15% segment was accessed during local preflight
SETTLEMENT_HOURS = (0, 8, 16)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def funding_exclusion(entry_time: pd.Timestamp) -> tuple[bool, pd.Timestamp]:
    """Exclude entries whose full 4h maximum hold reaches/crosses next UTC settlement."""
    next_time = eth.next_settlement(pd.Timestamp(entry_time))
    return (pd.Timestamp(entry_time) + MAX_HOLD_BARS * BAR >= next_time), next_time


def eligible_signals(data: pd.DataFrame, signals: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, excluded = [], []
    for signal in signals:
        entry_i = int(signal["entry_i"])
        if entry_i >= len(data):
            continue
        entry_time = data.index[entry_i]
        exclude, settlement = funding_exclusion(entry_time)
        if exclude:
            excluded.append({
                "signal_time": data.index[int(signal["signal_i"])].isoformat(),
                "entry_time": entry_time.isoformat(),
                "utc_hour": int(entry_time.hour),
                "next_settlement": settlement.isoformat(),
                "reason": "maximum_4h_horizon_reaches_or_crosses_funding_settlement",
            })
        else:
            kept.append(signal)
    return kept, excluded


def apply_cost(trades: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        return result
    side = result.side.to_numpy()
    entry = result.entry.to_numpy(float)
    stop = result.stop.to_numpy(float)
    risk = np.where(side == "long", entry - stop, stop - entry)
    if not np.isfinite(risk).all() or (risk <= 0).any():
        raise RuntimeError("Trade ledger contains non-positive or invalid initial risk")
    result["cost_R"] = entry * (cost_bps / 10000.0) / risk
    result["net_R"] = result.gross_R.astype(float) - result.cost_R
    result["cost_bps"] = float(cost_bps)
    return result


def add_completed_4h_regime(raw: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        result["regime"] = pd.Series(dtype=str)
        return result
    h4 = eth.aggregate_4h(raw)
    parts = []
    for _, group in h4.groupby("segment", sort=True):
        frame = group.copy()
        frame["ema50"] = frame.close.ewm(span=50, adjust=False, min_periods=50).mean()
        frame["ema200"] = frame.close.ewm(span=200, adjust=False, min_periods=200).mean()
        bull = (frame.close > frame.ema50) & (frame.ema50 > frame.ema200)
        bear = (frame.close < frame.ema50) & (frame.ema50 < frame.ema200)
        frame["regime"] = np.select([bull, bear], ["bull", "bear"], default="neutral")
        parts.append(frame[["regime"]])
    regimes = pd.concat(parts).sort_index()
    entry_times = pd.DatetimeIndex(result.entry_time)
    aligned = regimes.regime.reindex(entry_times, method="ffill")
    result["regime"] = aligned.to_numpy()
    result["regime"] = result.regime.fillna("unavailable")
    return result


def first_touch_ambiguity(data: pd.DataFrame, trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "first_touch_ambiguous_bars": 0, "stop_gap_fills": 0}
    index = data.index
    ambiguous = 0
    stop_gap_fills = 0
    for trade in trades.to_dict("records"):
        entry_i = int(index.get_indexer([pd.Timestamp(trade["entry_time"])])[0])
        exit_i = int(index.get_indexer([pd.Timestamp(trade["exit_time"])])[0])
        side = trade["side"]
        stop = float(trade["stop"])
        target = float(trade["target"])
        first_touch = None
        for i in range(entry_i, exit_i + 1):
            row = data.iloc[i]
            stop_hit = row.low <= stop if side == "long" else row.high >= stop
            target_hit = row.high >= target if side == "long" else row.low <= target
            if stop_hit and target_hit:
                ambiguous += 1
                first_touch = "ambiguous"
                break
            if stop_hit:
                first_touch = "stop"
                break
            if target_hit:
                first_touch = "target"
                break
        if trade["outcome"] == "SL" and first_touch == "stop":
            opening = float(data.open.iloc[exit_i])
            if (side == "long" and opening < stop) or (side == "short" and opening > stop):
                stop_gap_fills += 1
    return {
        "trades": int(len(trades)),
        "first_touch_ambiguous_bars": int(ambiguous),
        "stop_gap_fills": int(stop_gap_fills),
    }


def sample_metrics(trades: pd.DataFrame, cost_bps: float) -> dict:
    return st.metrics(apply_cost(trades, cost_bps))


def split_gates(train: dict, validation: dict) -> dict:
    train_pass = (
        train["trades"] >= MIN_TRAIN_TRADES
        and train["net_R"] > 0
        and train["profit_factor"] is not None
        and train["profit_factor"] >= MIN_PF
        and train["max_drawdown_R"] >= -25.0
        and train["positive_month_fraction"] >= MIN_POSITIVE_MONTH_FRACTION
    )
    validation_pass = (
        validation["trades"] >= MIN_VALIDATION_TRADES
        and validation["net_R"] > 0
        and validation["profit_factor"] is not None
        and validation["profit_factor"] >= MIN_PF
        and validation["max_drawdown_R"] >= -15.0
        and validation["positive_month_fraction"] >= MIN_POSITIVE_MONTH_FRACTION
    )
    return {
        "train_pass": bool(train_pass),
        "validation_pass": bool(validation_pass),
        "development_validation_pass": bool(train_pass and validation_pass),
        "oos_eligible": False,
    }


def monthly_rows(trades: pd.DataFrame, sample: str) -> list[dict]:
    if trades.empty:
        return []
    frame = trades.copy()
    frame["month"] = pd.to_datetime(frame.entry_time, utc=True).dt.strftime("%Y-%m")
    rows = []
    for month, group in frame.groupby("month", sort=True):
        rows.append({"sample": sample, "month": month, **st.metrics(group)})
    return rows


def regime_rows(trades: pd.DataFrame, sample: str) -> list[dict]:
    if trades.empty:
        return []
    return [
        {"sample": sample, "regime": str(regime), **st.metrics(group)}
        for regime, group in trades.groupby("regime", dropna=False, sort=True)
    ]


def self_test() -> list[str]:
    assert funding_exclusion(pd.Timestamp("2026-11-20T03:45:00Z"))[0] is False
    assert funding_exclusion(pd.Timestamp("2026-11-20T04:00:00Z"))[0] is True
    assert funding_exclusion(pd.Timestamp("2026-11-20T08:00:00Z"))[0] is False

    fixture = pd.DataFrame([{
        "side": "long", "entry": 100.0, "stop": 99.0, "gross_R": 1.0,
        "exit": 101.0, "target": 102.0, "outcome": "TIME",
        "entry_time": pd.Timestamp("2026-01-01T00:00:00Z"),
        "exit_time": pd.Timestamp("2026-01-01T03:45:00Z"),
        "signal_time": pd.Timestamp("2025-12-31T23:45:00Z"),
    }])
    assert abs(float(apply_cost(fixture, 12.0).net_R.iloc[0]) - 0.88) < 1e-12
    assert abs(float(apply_cost(fixture, 6.0).net_R.iloc[0]) - 0.94) < 1e-12

    idx = pd.date_range("2026-01-01", periods=500, freq="15min", tz="UTC")
    rng = np.random.default_rng(20261120)
    close = 2000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.001, len(idx))))
    frame = pd.DataFrame({
        "open": close, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": 1.0,
    }, index=idx)
    prepared, tr, _ = st.prepare_base(frame)
    atr_a, direction_a, line_a = st.build_supertrend(prepared, tr, ATR_SOURCE, ATR_LENGTH, ATR_MULTIPLIER)
    changed = frame.copy()
    for column in ("open", "high", "low", "close"):
        changed.iloc[350:, changed.columns.get_loc(column)] *= 1.25
    prepared_b, tr_b, _ = st.prepare_base(changed)
    atr_b, direction_b, line_b = st.build_supertrend(prepared_b, tr_b, ATR_SOURCE, ATR_LENGTH, ATR_MULTIPLIER)
    for left, right in ((atr_a, atr_b), (line_a, line_b)):
        assert np.allclose(left.iloc[:350], right.iloc[:350], equal_nan=True)
    assert np.array_equal(direction_a[:350], direction_b[:350])
    assert OOS_EVALUATION_ENABLED is False
    assert split_gates(
        {"trades": 0, "net_R": 0, "profit_factor": None, "max_drawdown_R": 0, "positive_month_fraction": 0},
        {"trades": 0, "net_R": 0, "profit_factor": None, "max_drawdown_R": 0, "positive_month_fraction": 0},
    )["oos_eligible"] is False
    return [
        "funding_boundary_entry_exclusion",
        "cost_R_conversion",
        "supertrend_future_perturbation_invariance",
        "contaminated_holdout_evaluation_disabled",
    ]


def run(output_dir: Path, csv_path: Path | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir = output_dir / "download"
    if csv_path is None:
        eth.download(download_dir)
        source_path = download_dir / "ETHUSDT_15m_binance.csv"
    else:
        source_path = csv_path
    raw = eth.load_source(source_path)
    if len(raw) < 20000:
        raise RuntimeError(f"Insufficient ETHUSDT 15m history: {len(raw)} rows")
    diffs = raw.index.to_series().diff().dropna()
    gap_count = int((diffs != BAR).sum())
    if gap_count:
        raise RuntimeError(f"Expected contiguous ETH source; found {gap_count} missing/irregular intervals")

    st.MAX_HOLD_BARS = MAX_HOLD_BARS
    st.COST_RATE = PRIMARY_COST_BPS / 10000.0
    data, tr, hourly = st.prepare_base(raw)
    signals_all = st.build_signals(data, tr, ATR_SOURCE, ATR_LENGTH, ATR_MULTIPLIER)
    signals, excluded = eligible_signals(data, signals_all)
    if not signals:
        raise RuntimeError("No settlement-safe Supertrend signals")
    pd.DataFrame(excluded, columns=["signal_time", "entry_time", "utc_hour", "next_settlement", "reason"]).to_csv(
        output_dir / "funding_excluded_signals.csv", index=False
    )

    n = len(data)
    train_end = int(n * TRAIN_FRACTION)
    validation_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    segments = {
        "development": (0, train_end),
        "validation": (train_end, validation_end),
        "final_holdout": (validation_end, n),
    }
    gap_mask = data.index.to_series().diff().ne(BAR).to_numpy(copy=True)
    gap_mask[0] = False
    config = {
        "config_id": "hl2_atr10_x3_2R_both_all_4h",
        "source": ATR_SOURCE, "atr_length": ATR_LENGTH,
        "atr_multiplier": ATR_MULTIPLIER, "target_r": TARGET_R,
        "filter": "none", "direction": "both", "session": "all",
    }
    trade_sets = {
        sample: st.simulate(data, signals, config, *segments[sample], gap_mask)
        for sample in ("development", "validation")
    }
    metrics_primary = {
        sample: sample_metrics(trades, PRIMARY_COST_BPS)
        for sample, trades in trade_sets.items()
    }
    gates = split_gates(metrics_primary["development"], metrics_primary["validation"])
    # The reserved 15% segment was inadvertently materialized during a local
    # preflight split-loop before the promotion gates were applied. Retire it:
    # never evaluate or report its performance from this study.
    metrics_primary["final_holdout"] = None
    oos_status = "retired_contaminated_by_local_preflight_access"

    regime_sets = {}
    for sample, trades in trade_sets.items():
        enriched = add_completed_4h_regime(raw, trades)
        enriched["signal_confirmed_at"] = pd.to_datetime(enriched.signal_time, utc=True) + BAR if not enriched.empty else pd.Series(dtype="datetime64[ns, UTC]")
        regime_sets[sample] = enriched
        enriched.to_csv(output_dir / f"{sample}_trades.csv", index=False)

    cost_rows = []
    for sample, trades in trade_sets.items():
        for cost in COSTS_BPS:
            cost_rows.append({"sample": sample, "cost_bps_round_trip": cost, **sample_metrics(trades, cost)})
    pd.DataFrame(cost_rows).to_csv(output_dir / "cost_sensitivity.csv", index=False)

    month_rows, regime_summary_rows, ambiguity = [], [], {}
    for sample, trades in regime_sets.items():
        adjusted = apply_cost(trades, PRIMARY_COST_BPS)
        month_rows.extend(monthly_rows(adjusted, sample))
        regime_summary_rows.extend(regime_rows(adjusted, sample))
        ambiguity[sample] = first_touch_ambiguity(data, trades)
    pd.DataFrame(month_rows).to_csv(output_dir / "monthly_results.csv", index=False)
    pd.DataFrame(regime_summary_rows).to_csv(output_dir / "regime_results.csv", index=False)

    download_dir = output_dir / "download"
    download_meta_path = download_dir / "download_metadata.json"
    manifest_path = download_dir / "archive_manifest.csv"
    download_meta = json.loads(download_meta_path.read_text()) if download_meta_path.exists() else {}
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    data_quality = {
        "venue": "Binance USDⓈ-M", "symbol": "ETHUSDT", "timeframe": "15m",
        "rows": int(len(data)), "start_utc": data.index.min().isoformat(),
        "end_open_utc": data.index.max().isoformat(), "missing_or_irregular_intervals": gap_count,
        "zero_volume_rows": int((raw.volume == 0).sum()), "complete_hourly_bars": int(len(hourly)),
        "source_sha256": sha256(source_path),
        "archive_count": int(download_meta.get("archive_count", len(manifest))),
        "checksum_verified_archives": int(download_meta.get("checksum_verified_archives", manifest.get("checksum_verified", pd.Series(dtype=bool)).astype(bool).sum())),
        "archive_manifest": str(manifest_path) if manifest_path.exists() else None,
    }
    split_metadata = {
        "development_start": data.index[0].isoformat(),
        "development_last_bar_open": data.index[train_end - 1].isoformat(),
        "validation_first_bar_open": data.index[train_end].isoformat(),
        "validation_last_bar_open": data.index[validation_end - 1].isoformat(),
        "final_holdout_first_bar_open": data.index[validation_end].isoformat(),
        "final_holdout_last_bar_open": data.index[-1].isoformat(),
        "row_fractions": {
            "development": TRAIN_FRACTION, "validation": VALIDATION_FRACTION,
            "retired_holdout": 1 - TRAIN_FRACTION - VALIDATION_FRACTION,
        },
        "retired_holdout_status": "not_evaluated_contaminated_by_local_preflight_access",
    }
    summary = {
        "status": "completed_validation_gates_passed_holdout_retired" if gates["development_validation_pass"] else "completed_validation_gates_failed_holdout_retired",
        "symbol": "ETHUSDT", "strategy": "15m Supertrend flip continuation",
        "configuration": config, "max_hold_bars": MAX_HOLD_BARS, "max_hold_hours": 4,
        "primary_cost_bps_round_trip": PRIMARY_COST_BPS, "cost_sensitivity_bps_round_trip": list(COSTS_BPS),
        "funding_exclusion": {
            "settlement_hours_utc": list(SETTLEMENT_HOURS),
            "excluded_signal_count": len(excluded), "eligible_signal_count": len(signals),
            "excluded_by_entry_hour": pd.DataFrame(excluded).groupby("utc_hour").size().to_dict() if excluded else {},
            "cashflows_applied": False,
        },
        "data_quality": data_quality, "splits": split_metadata,
        "signal_count_before_funding_exclusion": len(signals_all),
        "train_gate": gates["train_pass"], "validation_gate": gates["validation_pass"],
        "development_validation_pass": gates["development_validation_pass"],
        "oos_evaluated": False, "oos_status": oos_status,
        "metrics_at_primary_cost": metrics_primary,
        "ambiguity_audit": ambiguity, "self_tests": self_test(),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    report = [
        "# ETHUSDT 15m Supertrend intraday cross-asset replication", "",
        f"- Status: {summary['status']}; OOS evaluated: {summary['oos_evaluated']}.",
        f"- Data: {data_quality['rows']:,} 15m bars; {data_quality['start_utc']} to {data_quality['end_open_utc']}; gaps/irregular intervals: {gap_count}; source SHA-256: {data_quality['source_sha256']}.",
        f"- Official archives: {data_quality['archive_count']}; checksum-verified: {data_quality['checksum_verified_archives']}.",
        f"- Frozen rule: HL2 Supertrend, Wilder ATR(10) x3, next-open entry, signal-bar line stop, 2R target, both directions, all hours, 4h maximum hold.",
        f"- Funding-safe entries: {len(signals):,} eligible / {len(signals_all):,} raw flips; {len(excluded):,} excluded because the full 4h horizon reached/crossed the next UTC funding settlement.",
        f"- Primary cost: assumed {PRIMARY_COST_BPS:.0f} bps round trip; funding cashflows are not applied because settlement-crossing entries are excluded.", "",
        "## Primary-cost results", "",
    ]
    for sample in ("development", "validation", "final_holdout"):
        result = metrics_primary.get(sample)
        if result is None:
            if sample == "final_holdout":
                report.append("- final_holdout: retired and not evaluated; the reserved segment was accidentally materialized during a local preflight before gates were applied. It must not be used for OOS claims.")
            else:
                report.append(f"- {sample}: not evaluated; the preregistered promotion gate was not met.")
            continue
        report.append(
            f"- {sample}: {result['trades']} trades, {result['profitable_pct']:.2f}% profitable, "
            f"PF {result['profit_factor']}, net {result['net_R']:.2f}R, avg {result['avg_R']:.3f}R, "
            f"max DD {result['max_drawdown_R']:.2f}R, losing streak {result['max_losing_streak']}, "
            f"positive months {result['positive_month_fraction']:.1%}; TP/SL/TIME "
            f"{result['TP']}/{result['SL']}/{result['TIME']}."
        )
    report += [
        "", "## Execution audit", "", json.dumps(ambiguity, indent=2), "",
        "## Limitations", "",
        "- 12 bps round trip is an assumption, not a verified account fee tier; separate spread, variable slippage and market impact are not modeled.",
        "- Entries whose maximum 4h horizon reaches/crosses a Binance UTC funding settlement are excluded; no funding cashflow is applied.",
        "- OHLC same-bar stop/target ambiguity is resolved stop-first; this is a conservative bar-level approximation, not tick replay.",
        "- R is normalized by initial stop distance and is not account return or equity drawdown.",
        "- Completed 4h regime is attribution only; it is not an entry filter.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eth_supertrend_intraday_results")
    parser.add_argument("--csv", default=None, help="Optional verified ETHUSDT 15m CSV; otherwise download official archives.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    tests = self_test()
    if args.self_test:
        for test in tests:
            print(f"PASS {test}")
        return
    result = run(Path(args.out), Path(args.csv) if args.csv else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
