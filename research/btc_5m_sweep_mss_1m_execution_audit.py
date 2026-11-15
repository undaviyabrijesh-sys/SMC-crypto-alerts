#!/usr/bin/env python3
"""Replay frozen BTC SMC 5m entries with 1m traded-price candles.

This is an execution-resolution audit only. Signals, 5m entry prices, stops,
targets and candidate configurations are frozen from the prior 5m study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import btc_5m_sweep_mss_execution_backtest as base

MINUTE = pd.Timedelta(minutes=1)
USER_AGENT = "SaltyQuantSMC1mExecutionAudit/1.0"
COSTS = (6, 12, 20)

# Frozen from the completed 2026-11-15 5m matrix. The second row is diagnostic
# only; it failed the training gate and is not a promotion candidate.
CANDIDATES = (
    {
        "label": "best_train_candidate",
        "ext_strength": 3, "local_strength": 3, "mss_wait": 8,
        "entry_mode": "next_open", "stop_buffer": 0.0, "target_r": 1.5,
        "htf_filter": "none", "direction": "both", "session": "all",
    },
    {
        "label": "best_validation_diagnostic_not_selected",
        "ext_strength": 3, "local_strength": 3, "mss_wait": 8,
        "entry_mode": "next_open", "stop_buffer": 0.1, "target_r": 2.0,
        "htf_filter": "none", "direction": "both", "session": "all",
    },
)


def digest_frame(frame: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for start in range(0, len(frame), 100_000):
        h.update(frame.iloc[start:start + 100_000].to_csv().encode())
    return h.hexdigest()


def fetch_1m() -> tuple[pd.DataFrame, dict]:
    now = pd.Timestamp.now(tz="UTC")
    end = int(now.timestamp())
    start = end - base.DAYS * 86400
    chunk_seconds = 1800 * 60  # 1,800 candles, below Delta's 2,000 limit
    frames = []
    cursor = start
    source_rows = 0

    while cursor < end:
        stop = min(cursor + chunk_seconds, end)
        response = requests.get(
            base.BASE,
            params={
                "resolution": "1m",
                "symbol": base.SYMBOL,
                "start": cursor,
                "end": stop,
            },
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is not True:
            raise RuntimeError(f"Delta API error: {payload}")
        rows = payload.get("result") or []
        if rows:
            part = pd.DataFrame(rows)
            source_rows += len(part)
            frames.append(part)
        cursor = stop
        time.sleep(0.08)

    if not frames:
        raise RuntimeError("Delta returned no BTCUSD 1m candles")

    raw = pd.concat(frames, ignore_index=True)
    raw["timestamp"] = pd.to_datetime(
        pd.to_numeric(raw["time"], errors="coerce"), unit="s", utc=True
    )
    invalid_timestamp = int(raw.timestamp.isna().sum())
    raw = raw.dropna(subset=["timestamp"])
    duplicates = int(raw.timestamp.duplicated().sum())
    raw = raw.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    raw = raw.set_index("timestamp")

    for col in ("open", "high", "low", "close"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    ohlc = raw[["open", "high", "low", "close"]].to_numpy(float)
    finite = np.isfinite(ohlc).all(axis=1)
    positive = (raw[["open", "high", "low", "close"]] > 0).all(axis=1).to_numpy()
    shape = (
        (raw.high >= raw[["open", "close", "low"]].max(axis=1))
        & (raw.low <= raw[["open", "close", "high"]].min(axis=1))
    ).to_numpy()
    invalid_nonfinite = int((~finite).sum())
    invalid_nonpositive = int((finite & ~positive).sum())
    invalid_shape = int((finite & positive & ~shape).sum())
    raw = raw.loc[finite & positive & shape]
    raw = raw.loc[raw.index + MINUTE <= now]

    diffs = raw.index.to_series().diff().dropna()
    gaps = int((diffs != MINUTE).sum())
    largest_gap = float(diffs.max().total_seconds() / 60) if len(diffs) else 0.0
    expected = int((raw.index[-1] - raw.index[0]).total_seconds() / 60) + 1
    quality = {
        "symbol": base.SYMBOL,
        "resolution": "1m",
        "source_rows": source_rows,
        "valid_rows": len(raw),
        "start_utc": raw.index.min().isoformat(),
        "end_utc": raw.index.max().isoformat(),
        "duplicate_rows_removed": duplicates,
        "invalid_timestamp_rows": invalid_timestamp,
        "invalid_nonfinite_ohlc_rows": invalid_nonfinite,
        "invalid_nonpositive_ohlc_rows": invalid_nonpositive,
        "invalid_ohlc_shape_rows": invalid_shape,
        "gap_count": gaps,
        "largest_gap_minutes": largest_gap,
        "observed_minute_coverage_fraction": float(len(raw) / expected) if expected else 0.0,
        "zero_volume_rows": (
            int((pd.to_numeric(raw.volume, errors="coerce") == 0).sum())
            if "volume" in raw else None
        ),
        "sha256": digest_frame(raw),
    }
    if raw.empty:
        raise RuntimeError("No valid closed BTCUSD 1m candles")
    return raw, quality


def compare_1m_to_5m(one: pd.DataFrame, five: pd.DataFrame) -> dict:
    agg = one[["open", "high", "low", "close"]].resample(
        "5min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = one.close.resample("5min", label="left", closed="left").count()
    agg = agg.loc[counts.eq(5)].dropna()
    joined = five[["open", "high", "low", "close"]].join(
        agg, how="inner", lsuffix="_5m", rsuffix="_1m"
    )
    if joined.empty:
        return {
            "complete_1m_derived_5m_bars": len(agg),
            "matched_native_5m_bars": 0,
            "ohlc_exact_match_fraction": None,
            "mismatched_bars": None,
            "max_abs_price_difference": None,
        }
    diffs = []
    exact = np.ones(len(joined), dtype=bool)
    for col in ("open", "high", "low", "close"):
        delta = (joined[f"{col}_5m"] - joined[f"{col}_1m"]).abs().to_numpy(float)
        diffs.append(delta)
        exact &= delta <= 1e-8
    all_diffs = np.concatenate(diffs)
    return {
        "complete_1m_derived_5m_bars": len(agg),
        "matched_native_5m_bars": len(joined),
        "ohlc_exact_match_fraction": float(exact.mean()),
        "mismatched_bars": int((~exact).sum()),
        "max_abs_price_difference": float(np.nanmax(all_diffs)),
    }


def replay_trade(trade: dict, one: pd.DataFrame) -> dict:
    start = pd.Timestamp(trade["entry_time"])
    exit_bar_start = pd.Timestamp(trade["exit_time"])
    end_exclusive = exit_bar_start + base.BAR
    expected_n = int((end_exclusive - start) / MINUTE)
    if expected_n <= 0:
        return {"replay_status": "invalid_window"}

    idx = one.index
    pos = int(idx.searchsorted(start, side="left"))
    side = str(trade["side"])
    entry = float(trade["entry"])
    stop = float(trade["stop"])
    target = float(trade["target"])
    risk = entry - stop if side == "long" else stop - entry
    if not np.isfinite(risk) or risk <= 0:
        return {"replay_status": "invalid_risk"}

    first_open_diff_pct = None
    for offset in range(expected_n):
        j = pos + offset
        expected_time = start + offset * MINUTE
        if j >= len(one) or idx[j] != expected_time:
            return {
                "replay_status": "unresolved_1m_gap",
                "minute_bars_seen": offset,
                "entry_open_diff_pct": first_open_diff_pct,
            }

        row = one.iloc[j]
        o, h, l, close = map(float, (row.open, row.high, row.low, row.close))
        if offset == 0:
            first_open_diff_pct = abs(o - entry) / entry * 100.0

        ambiguous = base.ambiguous_stop_target(side, o, h, l, stop, target)
        px, outcome = base.fill_exit(side, o, h, l, stop, target)
        if outcome:
            exit_price = float(px)
            optimistic_exit = target if ambiguous else exit_price
            gross = (
                (exit_price - entry) / risk
                if side == "long" else (entry - exit_price) / risk
            )
            optimistic_gross = (
                (optimistic_exit - entry) / risk
                if side == "long" else (entry - optimistic_exit) / risk
            )
            return {
                "replay_status": "resolved",
                "replay_exit_time": expected_time.isoformat(),
                "replay_exit": exit_price,
                "replay_outcome": outcome,
                "replay_gross_R": gross,
                "replay_optimistic_gross_R": optimistic_gross,
                "ambiguous_1m_bar": bool(ambiguous),
                "minute_bars_seen": offset + 1,
                "entry_open_diff_pct": first_open_diff_pct,
            }

    last_time = start + (expected_n - 1) * MINUTE
    last_close = float(one.iloc[pos + expected_n - 1].close)
    gross = (
        (last_close - entry) / risk
        if side == "long" else (entry - last_close) / risk
    )
    return {
        "replay_status": "resolved",
        "replay_exit_time": last_time.isoformat(),
        "replay_exit": last_close,
        "replay_outcome": "TIME",
        "replay_gross_R": gross,
        "replay_optimistic_gross_R": gross,
        "ambiguous_1m_bar": False,
        "minute_bars_seen": expected_n,
        "entry_open_diff_pct": first_open_diff_pct,
    }


def summarise_replays(trades: pd.DataFrame) -> list[dict]:
    output = []
    for (label, sample), group in trades.groupby(["candidate", "sample"]):
        resolved = group.loc[group.replay_status == "resolved"].copy()
        unresolved = int((group.replay_status != "resolved").sum())
        for cost_bps in COSTS:
            if resolved.empty:
                output.append({
                    "candidate": label, "sample": sample, "cost_bps": cost_bps,
                    "five_minute_trades": len(group), "resolved_1m_trades": 0,
                    "unresolved_1m_trades": unresolved,
                })
                continue
            risk = np.where(
                resolved.side.eq("long"),
                resolved.entry - resolved.stop,
                resolved.stop - resolved.entry,
            )
            cost_r = (cost_bps / 10000.0) * resolved.entry.to_numpy(float) / risk
            m = resolved.copy()
            m["net_R"] = m.replay_gross_R.to_numpy(float) - cost_r
            m["optimistic_net_R"] = (
                m.replay_optimistic_gross_R.to_numpy(float) - cost_r
            )
            m["outcome"] = m.replay_outcome
            m["ambiguous_stop_target_bar"] = m.ambiguous_1m_bar
            metrics = base.metrics(m)
            output.append({
                "candidate": label, "sample": sample, "cost_bps": cost_bps,
                "five_minute_trades": len(group),
                "resolved_1m_trades": len(resolved),
                "unresolved_1m_trades": unresolved,
                "entry_open_mismatch_over_0_01pct": int(
                    (resolved.entry_open_diff_pct > 0.01).sum()
                ),
                "max_entry_open_difference_pct": float(
                    resolved.entry_open_diff_pct.max()
                ),
                **metrics,
            })
    return output


def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw5 = base.fetch_5m()
    five, m15, h1, h4 = base.prepare(raw5)
    one, quality1 = fetch_1m()

    n = len(five)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    splits = {
        "train": (0, train_end),
        "validation": (train_end, val_end),
    }

    events = base.build_events(m15, h1, 3, 3, 8)
    entries = base.build_entries(five, m15, events, "next_open")
    all_rows = []

    for candidate in CANDIDATES:
        cfg = {k: v for k, v in candidate.items() if k != "label"}
        for sample, (start_i, end_i) in splits.items():
            trades = base.simulate(
                five, entries, {**cfg, "sample": sample},
                start_i, end_i, 12,
            )
            for row in trades.to_dict("records"):
                replay = replay_trade(row, one)
                all_rows.append({
                    **row,
                    "candidate": candidate["label"],
                    **replay,
                })

    trades = pd.DataFrame(all_rows)
    if trades.empty:
        raise RuntimeError("No frozen-candidate trades were generated")
    trades.to_csv(output_dir / "frozen_candidate_1m_replay_trades.csv", index=False)
    summary = pd.DataFrame(summarise_replays(trades))
    summary.to_csv(output_dir / "frozen_candidate_1m_replay_summary.csv", index=False)

    alignment = compare_1m_to_5m(one, five)
    (output_dir / "one_minute_five_minute_alignment.json").write_text(
        json.dumps(alignment, indent=2) + "\n"
    )

    gaps5 = int((five.index.to_series().diff().dropna() != base.BAR).sum())
    metadata = {
        "classification": "experimental execution audit only; no live use",
        "symbol": base.SYMBOL,
        "five_minute_rows": len(five),
        "five_minute_start_utc": five.index.min().isoformat(),
        "five_minute_end_utc": five.index.max().isoformat(),
        "five_minute_gaps": gaps5,
        "five_minute_sha256": hashlib.sha256(raw5.to_csv().encode()).hexdigest(),
        "one_minute_quality": quality1,
        "one_minute_to_five_minute_alignment": alignment,
        "candidates": list(CANDIDATES),
        "split": "chronological 70/15/15 by the 5m row index; train and validation only",
        "entry": "unchanged 5m next-open signal and fill; no 1m signal or entry optimization",
        "exit": "1m first-touch replay; opening gaps first; stop-first on ambiguous 1m bars; target-first upper bound reported",
        "maximum_holding_period": "4 hours",
        "costs": "6/12/20bp round-trip assumptions; funding, spread and market impact excluded",
        "oos_evaluated": False,
        "decision_rule": "no promotion; preceding 5m matrix had zero validation passes",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n"
    )
    print(json.dumps(metadata, indent=2, default=str))
    print("\n1M REPLAY SUMMARY")
    print(summary.to_string(index=False))


def self_test() -> None:
    idx = pd.date_range(
        "2026-01-01T00:00:00Z", periods=10, freq="1min"
    )
    synthetic = pd.DataFrame(
        {"open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0},
        index=idx,
    )
    synthetic.loc[idx[2], ["high", "low"]] = [111.0, 89.0]
    trade = {
        "side": "long", "entry_time": idx[0], "exit_time": idx[5],
        "entry": 100.0, "stop": 90.0, "target": 110.0,
    }
    result = replay_trade(trade, synthetic)
    assert result["replay_status"] == "resolved"
    assert result["replay_outcome"] == "SL"
    assert result["ambiguous_1m_bar"] is True
    assert result["replay_optimistic_gross_R"] > result["replay_gross_R"]

    gap = synthetic.drop(idx[1])
    gap_result = replay_trade(trade, gap)
    assert gap_result["replay_status"] == "unresolved_1m_gap"

    target_first = synthetic.copy()
    target_first.loc[idx[2], ["high", "low"]] = [111.0, 95.0]
    target_result = replay_trade(trade, target_first)
    assert target_result["replay_outcome"] == "TP"
    assert target_result["ambiguous_1m_bar"] is False
    print("1m replay synthetic tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("btc-5m-sweep-mss-1m-audit"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    run(args.output_dir)


if __name__ == "__main__":
    main()
