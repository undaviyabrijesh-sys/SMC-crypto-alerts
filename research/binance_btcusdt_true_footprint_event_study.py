"""Frozen multi-month BTCUSDT true-footprint descriptive event study.

This is an event study, not a stop-defined strategy backtest. It does not model
funding, spread, slippage, market impact, leverage, stops, targets or account PnL.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FAMILIES = ("absorption", "continuation")
DIRECTIONS = ("long", "short")
HORIZONS = (12, 48)
HORIZON_LABELS = {12: "1h", 48: "4h"}
COOLDOWN_BARS = 48
WARMUP_BARS = 288
TAIL_CENSOR_BARS = 48
ROUND_TRIP_COST_BPS = 10.0
ALIGNMENT_TOLERANCE = 0.001
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_BASE_SEED = 20261119
BAR_MS = 300_000
MIN_IMBALANCE_QTY = 0.10
IMBALANCE_RATIO = 3.0
PRICE_TICK_SCALE = 10

EVENT_COLUMNS = [
    "month", "family", "direction", "horizon_bars", "horizon",
    "signal_time_utc", "entry_time_utc", "exit_time_utc", "day_utc",
    "entry_price", "exit_price", "gross_bps", "cost_bps", "net_bps",
    "per_bar_alignment_ok",
]


def load_builder():
    path = Path(__file__).with_name("binance_btcusdt_true_footprint_build.py")
    spec = importlib.util.spec_from_file_location("salty_footprint_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the existing footprint builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def relative_error(actual: np.ndarray, reference: np.ndarray) -> np.ndarray:
    actual = np.asarray(actual, dtype=float)
    reference = np.asarray(reference, dtype=float)
    result = np.full(reference.shape, np.inf, dtype=float)
    positive = reference > 0
    result[positive] = np.abs(actual[positive] - reference[positive]) / reference[positive]
    both_zero = (~positive) & (actual == 0)
    result[both_zero] = 0.0
    return result


def max_consecutive_ticks(ticks: np.ndarray | list[int]) -> int:
    values = np.asarray(ticks, dtype=np.int64)
    if len(values) == 0:
        return 0
    values = np.sort(np.unique(values))
    run = best = 1
    for diff in np.diff(values):
        run = run + 1 if diff == 1 else 1
        best = max(best, run)
    return int(best)


def stack_bars(footprint: pd.DataFrame) -> tuple[set[int], set[int]]:
    required = {"bar_open_ms", "price_tick", "taker_buy_qty", "taker_sell_qty"}
    if not required.issubset(footprint.columns):
        raise ValueError(f"Footprint table missing columns: {sorted(required - set(footprint.columns))}")
    levels = footprint[list(required)].copy()
    levels["bar_open_ms"] = pd.to_numeric(levels.bar_open_ms, errors="raise").astype(np.int64)
    levels["price_tick"] = pd.to_numeric(levels.price_tick, errors="raise").astype(np.int64)
    levels["taker_buy_qty"] = pd.to_numeric(levels.taker_buy_qty, errors="raise").astype(float)
    levels["taker_sell_qty"] = pd.to_numeric(levels.taker_sell_qty, errors="raise").astype(float)
    if levels.duplicated(["bar_open_ms", "price_tick"]).any():
        raise ValueError("Duplicate (bar_open_ms, price_tick) footprint key")
    levels.sort_values(["bar_open_ms", "price_tick"], kind="mergesort", inplace=True)
    grouped = levels.groupby("bar_open_ms", sort=False)
    levels["previous_tick"] = grouped.price_tick.shift(1)
    levels["previous_sell"] = grouped.taker_sell_qty.shift(1)
    levels["next_tick"] = grouped.price_tick.shift(-1)
    levels["next_buy"] = grouped.taker_buy_qty.shift(-1)
    buy_flag = (
        (levels.price_tick - levels.previous_tick == 1)
        & (levels.taker_buy_qty >= IMBALANCE_RATIO * levels.previous_sell.fillna(0.0))
        & (levels.taker_buy_qty >= MIN_IMBALANCE_QTY)
    )
    sell_flag = (
        (levels.next_tick - levels.price_tick == 1)
        & (levels.taker_sell_qty >= IMBALANCE_RATIO * levels.next_buy.fillna(0.0))
        & (levels.taker_sell_qty >= MIN_IMBALANCE_QTY)
    )

    def bars_with_stack(mask: pd.Series) -> set[int]:
        selected = levels.loc[mask, ["bar_open_ms", "price_tick"]].copy()
        if selected.empty:
            return set()
        selected["break"] = selected.groupby("bar_open_ms", sort=False).price_tick.diff().ne(1)
        selected["run_id"] = selected.groupby("bar_open_ms", sort=False)["break"].cumsum()
        run_lengths = selected.groupby(["bar_open_ms", "run_id"], sort=False).size()
        qualifying = run_lengths[run_lengths >= 3]
        return set(int(value) for value in qualifying.index.get_level_values(0).unique())

    return bars_with_stack(buy_flag), bars_with_stack(sell_flag)


def select_with_cooldown(candidates: list[tuple[int, str]], cooldown: int = COOLDOWN_BARS) -> list[tuple[int, str]]:
    selected: list[tuple[int, str]] = []
    last_index: int | None = None
    for index, direction in sorted(candidates, key=lambda item: (item[0], item[1])):
        if last_index is None or index - last_index >= cooldown:
            selected.append((int(index), direction))
            last_index = int(index)
    return selected


def calculate_net_bps(direction: str, entry: float, exit_price: float,
                      cost_bps: float = ROUND_TRIP_COST_BPS) -> tuple[float, float]:
    if entry <= 0 or exit_price <= 0:
        raise ValueError("Event-study entry and exit prices must be positive")
    sign = 1.0 if direction == "long" else -1.0
    gross = sign * (exit_price / entry - 1.0) * 10_000.0
    return float(gross), float(gross - cost_bps)


def max_losing_streak(values: np.ndarray) -> int:
    best = current = 0
    for value in values:
        if value <= 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)


def day_cluster_ci(events: pd.DataFrame, seed: int) -> tuple[float | None, float | None, int]:
    if events.empty:
        return None, None, 0
    clusters = [
        group.net_bps.to_numpy(dtype=float)
        for _, group in events.groupby("day_utc", sort=True)
        if len(group)
    ]
    if len(clusters) < 2:
        return None, None, len(clusters)
    rng = np.random.default_rng(seed)
    means = np.empty(BOOTSTRAP_REPS, dtype=float)
    for rep in range(BOOTSTRAP_REPS):
        chosen = rng.integers(0, len(clusters), size=len(clusters))
        sample = np.concatenate([clusters[int(index)] for index in chosen])
        means[rep] = float(sample.mean())
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high), len(clusters)


def summarize_group(events: pd.DataFrame, month: str, family: str,
                    direction: str, horizon: int) -> tuple[dict[str, Any], dict[str, Any]]:
    group = events[
        (events.family == family)
        & (events.direction == direction)
        & (events.horizon_bars == horizon)
    ].sort_values("signal_time_utc")
    values = group.net_bps.to_numpy(dtype=float)
    wins = values > 0
    positive_sum = float(values[values > 0].sum()) if len(values) else 0.0
    negative_sum = float(-values[values < 0].sum()) if len(values) else 0.0
    pf = positive_sum / negative_sum if negative_sum > 0 else None
    cumulative = np.cumsum(values) if len(values) else np.asarray([], dtype=float)
    if len(cumulative):
        peaks = np.maximum.accumulate(np.maximum(cumulative, 0.0))
        max_dd = float(np.min(cumulative - peaks))
    else:
        max_dd = None
    day_totals = group.groupby("day_utc").net_bps.sum() if len(group) else pd.Series(dtype=float)
    positive_days = int((day_totals > 0).sum())
    ci_seed = BOOTSTRAP_BASE_SEED + sum(ord(ch) for ch in f"{month}|{family}|{direction}|{horizon}")
    ci_low, ci_high, cluster_days = day_cluster_ci(group, ci_seed)
    summary = {
        "month": month,
        "family": family,
        "direction": direction,
        "horizon": HORIZON_LABELS[horizon],
        "horizon_bars": horizon,
        "event_count": int(len(group)),
        "win_rate_after_cost_pct": float(wins.mean() * 100.0) if len(values) else None,
        "descriptive_pf": float(pf) if pf is not None else None,
        "mean_net_bps": float(values.mean()) if len(values) else None,
        "median_net_bps": float(np.median(values)) if len(values) else None,
        "event_sequence_max_dd_bps": max_dd,
        "max_losing_streak": max_losing_streak(values),
        "positive_utc_days": positive_days,
        "event_days": int(day_totals.size),
    }
    bootstrap = {
        "month": month,
        "family": family,
        "direction": direction,
        "horizon": HORIZON_LABELS[horizon],
        "event_count": int(len(group)),
        "event_days": cluster_days,
        "mean_net_bps": float(values.mean()) if len(values) else None,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "bootstrap_reps": BOOTSTRAP_REPS if cluster_days >= 2 else 0,
    }
    return summary, bootstrap


def summarize_all(events: pd.DataFrame, month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries: list[dict[str, Any]] = []
    bootstraps: list[dict[str, Any]] = []
    for family in FAMILIES:
        for direction in DIRECTIONS:
            for horizon in HORIZONS:
                summary, bootstrap = summarize_group(events, month, family, direction, horizon)
                summaries.append(summary)
                bootstraps.append(bootstrap)
    return pd.DataFrame(summaries), pd.DataFrame(bootstraps)


def load_month(input_dir: Path, month: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    metadata_path = input_dir / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Missing feature metadata: {metadata_path}")
    feature_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    if feature_meta.get("month") != month or feature_meta.get("status") != "PASS":
        raise ValueError(f"Feature artifact is not PASS for {month}")

    builder = load_builder()
    builder.configure_month(month)
    kline_path = input_dir / "source" / f"BTCUSDT-5m-{month}.zip"
    klines, kline_meta = builder.read_klines(kline_path)
    recon_path = input_dir / "reconciliation_5m.csv"
    footprint_path = input_dir / "footprint_5m_price_levels.csv.gz"
    if not recon_path.is_file() or not footprint_path.is_file():
        raise FileNotFoundError("Missing per-bar reconciliation or exact-price footprint table")
    recon = pd.read_csv(recon_path)
    required_recon = {"open_time_ms", "agg_volume", "agg_taker_buy"}
    if not required_recon.issubset(recon.columns):
        raise ValueError(f"Reconciliation table missing {sorted(required_recon - set(recon.columns))}")
    frame = klines.merge(
        recon[["open_time_ms", "agg_volume", "agg_taker_buy"]],
        on="open_time_ms", how="left", validate="one_to_one",
    )
    if frame[["agg_volume", "agg_taker_buy"]].isna().any().any():
        raise ValueError("Missing per-bar aggregate-trade reconciliation values")
    frame["volume_error"] = relative_error(frame.agg_volume.to_numpy(), frame.volume.to_numpy())
    frame["taker_buy_error"] = relative_error(frame.agg_taker_buy.to_numpy(), frame.taker_buy_base.to_numpy())
    frame["alignment_ok"] = (
        (frame.volume_error <= ALIGNMENT_TOLERANCE)
        & (frame.taker_buy_error <= ALIGNMENT_TOLERANCE)
    )
    frame["delta_fraction_kline"] = np.where(
        frame.volume.to_numpy() > 0,
        (2.0 * frame.taker_buy_base.to_numpy() - frame.volume.to_numpy()) / frame.volume.to_numpy(),
        np.nan,
    )
    candle_range = frame.high - frame.low
    frame["close_location"] = np.where(
        candle_range.to_numpy() > 0,
        (frame.close.to_numpy() - frame.low.to_numpy()) / candle_range.to_numpy(),
        np.nan,
    )
    rolling_mean = frame.delta_fraction_kline.rolling(288, min_periods=96).mean().shift(1)
    rolling_std = frame.delta_fraction_kline.rolling(288, min_periods=96).std(ddof=0).shift(1)
    frame["delta_z_kline"] = (frame.delta_fraction_kline - rolling_mean) / rolling_std.replace(0.0, np.nan)

    footprint = pd.read_csv(
        footprint_path,
        usecols=["bar_open_ms", "price_tick", "taker_buy_qty", "taker_sell_qty"],
        dtype={"bar_open_ms": "int64", "price_tick": "int64",
               "taker_buy_qty": "float64", "taker_sell_qty": "float64"},
    )
    buy_stack_bars, sell_stack_bars = stack_bars(footprint)
    frame["buy_stack"] = frame.open_time_ms.isin(buy_stack_bars)
    frame["sell_stack"] = frame.open_time_ms.isin(sell_stack_bars)
    frame["month"] = month
    frame["signal_index"] = np.arange(len(frame), dtype=np.int64)
    return frame, {
        "feature_status": feature_meta.get("status"),
        "feature_aggtrade_rows": feature_meta.get("aggtrade_rows"),
        "feature_price_level_rows": feature_meta.get("price_level_rows"),
        "kline_rows": int(len(klines)),
        "kline_zip_crc_pass": bool(kline_meta.get("zip_crc_pass")),
        "alignment_eligible_bars": int(frame.alignment_ok.sum()),
        "alignment_excluded_bars": int((~frame.alignment_ok).sum()),
        "alignment_tolerance": ALIGNMENT_TOLERANCE,
        "volume_error_p95": float(frame.volume_error.quantile(0.95)),
        "volume_error_max": float(frame.volume_error.max()),
        "taker_buy_error_p95": float(frame.taker_buy_error.quantile(0.95)),
        "taker_buy_error_max": float(frame.taker_buy_error.max()),
    }


def build_events(frame: pd.DataFrame, month: str) -> pd.DataFrame:
    count = len(frame)
    candidates: dict[str, list[tuple[int, str]]] = {family: [] for family in FAMILIES}
    for index in range(WARMUP_BARS, max(WARMUP_BARS, count - TAIL_CENSOR_BARS)):
        row = frame.iloc[index]
        location = row.close_location
        if not np.isfinite(location):
            continue
        z = row.delta_z_kline
        if np.isfinite(z):
            if z >= 2.0 and location <= 0.25:
                candidates["absorption"].append((index, "short"))
            elif z <= -2.0 and location >= 0.75:
                candidates["absorption"].append((index, "long"))

        # Continuation uses exact-price aggTrade imbalance only on bars that
        # pass the frozen 0.10% per-bar kline reconciliation screen.
        if bool(row.alignment_ok):
            long_event = bool(row.buy_stack) and location >= 0.75
            short_event = bool(row.sell_stack) and location <= 0.25
            # A bar qualifying in both directions is ambiguous and is excluded.
            if long_event != short_event:
                candidates["continuation"].append((index, "long" if long_event else "short"))

    records: list[dict[str, Any]] = []
    times = frame.open_time_ms.to_numpy(np.int64)
    opens = frame.open.to_numpy(float)
    closes = frame.close.to_numpy(float)
    alignment = frame.alignment_ok.to_numpy(bool)
    for family in FAMILIES:
        selected = select_with_cooldown(candidates[family])
        for index, direction in selected:
            entry_index = index + 1
            signal_time = int(times[index] + BAR_MS)
            for horizon in HORIZONS:
                exit_index = index + horizon
                if entry_index >= count or exit_index >= count:
                    continue
                entry = float(opens[entry_index])
                exit_price = float(closes[exit_index])
                gross, net = calculate_net_bps(direction, entry, exit_price)
                signal_stamp = pd.to_datetime(signal_time, unit="ms", utc=True)
                entry_stamp = pd.to_datetime(times[entry_index], unit="ms", utc=True)
                exit_stamp = pd.to_datetime(times[exit_index] + BAR_MS, unit="ms", utc=True)
                records.append({
                    "month": month,
                    "family": family,
                    "direction": direction,
                    "horizon_bars": horizon,
                    "horizon": HORIZON_LABELS[horizon],
                    "signal_time_utc": signal_stamp.isoformat(),
                    "entry_time_utc": entry_stamp.isoformat(),
                    "exit_time_utc": exit_stamp.isoformat(),
                    "day_utc": signal_stamp.strftime("%Y-%m-%d"),
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "gross_bps": gross,
                    "cost_bps": ROUND_TRIP_COST_BPS,
                    "net_bps": net,
                    "per_bar_alignment_ok": bool(alignment[index]),
                })
    return pd.DataFrame(records, columns=EVENT_COLUMNS)


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in frame[columns].iterrows():
        values = []
        for column in columns:
            value = row[column]
            if pd.isna(value):
                values.append("—")
            elif isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.4f}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, divider] + rows)


def run_month(month: str, input_dir: Path, output_dir: Path) -> int:
    frame, data_meta = load_month(input_dir, month)
    events = build_events(frame, month)
    summary, bootstrap = summarize_all(events, month)
    output_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(output_dir / "events.csv", index=False, float_format="%.12g")
    summary.to_csv(output_dir / "summary.csv", index=False, float_format="%.12g")
    bootstrap.to_csv(output_dir / "bootstrap.csv", index=False, float_format="%.12g")
    meta = {
        "status": "COMPLETED",
        "month": month,
        "source_feature_status": data_meta["feature_status"],
        "source_feature_aggtrade_rows": data_meta["feature_aggtrade_rows"],
        "source_feature_price_level_rows": data_meta["feature_price_level_rows"],
        "kline_rows": data_meta["kline_rows"],
        "alignment": {key: value for key, value in data_meta.items() if key.startswith("alignment_") or key.endswith("_error_p95") or key.endswith("_error_max")},
        "events": int(len(events)),
        "summary_rows": int(len(summary)),
        "bootstrap_reps_per_group": BOOTSTRAP_REPS,
        "round_trip_cost_bps": ROUND_TRIP_COST_BPS,
        "strategy_backtest_run": False,
        "funding_modeled": False,
        "stop_target_modeled": False,
        "parameter_search": False,
        "method": "official-kline bar delta for absorption; exact-price aggTrade imbalance for continuation on bars with <=0.10% total-volume and taker-buy reconciliation error",
    }
    (output_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    report = [
        f"# BTCUSDT {month} frozen true-footprint event study",
        "",
        "**Status: completed descriptive event study; not a strategy validation or promotion test.**",
        "",
        f"- Official 5m kline rows: {data_meta['kline_rows']}",
        f"- Exact-price aggTrade rows in feature metadata: {data_meta['feature_aggtrade_rows']}",
        f"- Exact-price footprint rows: {data_meta['feature_price_level_rows']}",
        f"- Per-bar alignment-eligible bars: {data_meta['alignment_eligible_bars']}",
        f"- Per-bar alignment-excluded bars: {data_meta['alignment_excluded_bars']}",
        f"- Total-volume relative error p95/max: {data_meta['volume_error_p95']:.8g} / {data_meta['volume_error_max']:.8g}",
        f"- Taker-buy relative error p95/max: {data_meta['taker_buy_error_p95']:.8g} / {data_meta['taker_buy_error_max']:.8g}",
        f"- Selected event count (before duplicating horizons): {int(events[['family','direction','signal_time_utc']].drop_duplicates().shape[0]) if len(events) else 0}",
        "",
        "## Frozen event definitions",
        "",
        "- Absorption: official Binance kline delta fraction = (2 × taker-buy base volume − total base volume) / total base volume; z-score against the preceding 288 completed 5m bars only, shifted one bar, minimum 96 prior observations, population standard deviation. Short: z ≥ +2 and close location ≤ 0.25. Long: z ≤ −2 and close location ≥ 0.75.",
        "- Continuation: at least three consecutive 0.1 USDT price ticks with diagonal buy/sell imbalance ratio ≥ 3 and numerator quantity ≥ 0.10 BTC; close location confirms direction. Event bars must pass ≤0.10% per-bar total-volume and taker-buy reconciliation.",
        "- A 48-bar global cooldown applies within each family across directions. First 288 bars and final 48 bars of each month are censored to avoid warm-up and cross-month horizon/cooldown leakage.",
        "- Signal is known at candle close; entry is next 5m open. Horizons are 12 and 48 bars, exit at the corresponding horizon close. 10 bps round-trip cost is deducted.",
        "",
        "## Descriptive results",
        "",
        markdown_table(summary, ["family", "direction", "horizon", "event_count", "win_rate_after_cost_pct", "descriptive_pf", "mean_net_bps", "median_net_bps", "event_sequence_max_dd_bps", "max_losing_streak", "positive_utc_days"]),
        "",
        "## Bootstrap",
        "",
        markdown_table(bootstrap, ["family", "direction", "horizon", "event_count", "event_days", "mean_net_bps", "ci95_low", "ci95_high"]),
        "",
        "No stop, target, funding cashflow, spread, slippage, market impact, leverage or account PnL is modeled. These are fixed-horizon event diagnostics in basis points, not R-multiple strategy results. No threshold was optimized and no strategy is promoted.",
    ]
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(meta, sort_keys=True))
    return 0


def run_aggregate(input_dir: Path, output_dir: Path) -> int:
    files = sorted(input_dir.glob("binance-btcusdt-footprint-event-study-*/events.csv"))
    if not files:
        raise FileNotFoundError(f"No monthly event-study artifacts found under {input_dir}")
    frames = [pd.read_csv(path) for path in files]
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=EVENT_COLUMNS)
    months = sorted(events.month.dropna().astype(str).unique().tolist()) if len(events) else []
    summary, bootstrap = summarize_all(events, "pooled")
    output_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(output_dir / "events_pooled.csv", index=False, float_format="%.12g")
    summary.to_csv(output_dir / "summary_pooled.csv", index=False, float_format="%.12g")
    bootstrap.to_csv(output_dir / "bootstrap_pooled.csv", index=False, float_format="%.12g")
    meta = {
        "status": "COMPLETED",
        "source_months": months,
        "source_event_files": [str(path) for path in files],
        "events": int(len(events)),
        "summary_rows": int(len(summary)),
        "bootstrap_reps_per_group": BOOTSTRAP_REPS,
        "round_trip_cost_bps": ROUND_TRIP_COST_BPS,
        "strategy_backtest_run": False,
        "funding_modeled": False,
        "stop_target_modeled": False,
        "parameter_search": False,
    }
    (output_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    report = [
        "# BTCUSDT June–September 2026 pooled true-footprint event study",
        "",
        "**Status: completed pooled descriptive event study; not a strategy validation or promotion test.**",
        "",
        f"- Source months: {', '.join(months) if months else 'unavailable'}",
        f"- Pooled event records (each event appears once per horizon): {len(events)}",
        f"- Day-cluster bootstrap: {BOOTSTRAP_REPS:,} resamples per family/direction/horizon, 95% percentile interval",
        "",
        markdown_table(summary, ["family", "direction", "horizon", "event_count", "win_rate_after_cost_pct", "descriptive_pf", "mean_net_bps", "median_net_bps", "event_sequence_max_dd_bps", "max_losing_streak", "positive_utc_days"]),
        "",
        markdown_table(bootstrap, ["family", "direction", "horizon", "event_count", "event_days", "mean_net_bps", "ci95_low", "ci95_high"]),
        "",
        "Pooled estimates are descriptive and must not be used to select a best side or month. No stops, targets, funding, spread, slippage, market impact or account PnL are modeled. No strategy is promoted.",
    ]
    (output_dir / "pooled_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(meta, sort_keys=True))
    return 0


def self_test() -> None:
    assert max_consecutive_ticks([100, 101, 102]) == 3
    assert max_consecutive_ticks([100, 102, 103]) == 2
    assert max_consecutive_ticks([]) == 0
    assert select_with_cooldown([(1, "long"), (20, "short"), (49, "long")]) == [(1, "long"), (49, "long")]
    gross, net = calculate_net_bps("long", 100.0, 101.0)
    assert abs(gross - 100.0) < 1e-9 and abs(net - 90.0) < 1e-9
    gross, net = calculate_net_bps("short", 100.0, 99.0)
    assert abs(gross - 100.0) < 1e-9 and abs(net - 90.0) < 1e-9
    errors = relative_error(np.array([100.0, 0.0, 1.0]), np.array([100.0, 0.0, 0.0]))
    assert errors[0] == 0.0 and errors[1] == 0.0 and np.isinf(errors[2])
    toy = pd.DataFrame({
        "family": ["absorption", "absorption"],
        "direction": ["long", "long"],
        "horizon_bars": [12, 12],
        "signal_time_utc": ["2026-06-01T00:00:00+00:00", "2026-06-02T00:00:00+00:00"],
        "day_utc": ["2026-06-01", "2026-06-02"],
        "net_bps": [20.0, -5.0],
    })
    summary, _ = summarize_group(toy, "test", "absorption", "long", 12)
    assert summary["event_count"] == 2 and summary["positive_utc_days"] == 1
    print("8 deterministic event-study tests passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month")
    parser.add_argument("--input-dir")
    parser.add_argument("--output-dir", default="results/footprint-event-study")
    parser.add_argument("--aggregate-dir")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    output_dir = Path(args.output_dir)
    if args.aggregate_dir:
        return run_aggregate(Path(args.aggregate_dir), output_dir)
    if not args.month or not args.input_dir:
        parser.error("--month and --input-dir are required for a monthly event study")
    return run_month(args.month, Path(args.input_dir), output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
