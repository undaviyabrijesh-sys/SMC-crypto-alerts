"""Exploratory OI-confirmed volatility-expansion screen; never feeds production alerts.

Inputs are extracted Delta archive CSV directories. The OI candle timestamp is
assumed to denote the candle open, so its close is aligned at timestamp + 1h.
This assumption must be reconciled against the endpoint before any live use.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = ("BTC", "ETH", "XAU")
ROLLING_HOURS = 720
MIN_HISTORY_HOURS = 168
HOLD_HOURS = 8


def resample_complete_hours(five_minute: pd.DataFrame) -> pd.DataFrame:
    """Build right-labelled hourly OHLCV bars only from 12 observed 5m candles."""
    frame = five_minute.copy()
    if "timestamp" in frame.columns:
        frame = frame.set_index("timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("5m input contains duplicate timestamps")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    hourly = frame.resample("1h", label="right", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), n=("close", "count"),
    )
    hourly = hourly.loc[hourly["n"].eq(12)].drop(columns="n")
    return hourly.dropna(subset=["open", "high", "low", "close"])


def align_oi_close_time(oi: pd.DataFrame) -> pd.Series:
    """Align hourly OI candle closes to the end of their timestamped hour."""
    frame = oi.copy()
    if "timestamp" in frame.columns:
        frame = frame.set_index("timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True) + pd.Timedelta(hours=1)
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("OI input contains duplicate timestamps")
    values = pd.to_numeric(frame["close"], errors="coerce")
    return values.where(np.isfinite(values) & values.gt(0))


def add_features(hourly: pd.DataFrame) -> pd.DataFrame:
    """Add causal 1h return, ATR and lagged rolling expansion thresholds."""
    frame = hourly.copy().sort_index()
    frame.index = pd.to_datetime(frame.index, utc=True)
    contiguous = frame.index.to_series().diff().eq(pd.Timedelta(hours=1))
    frame["ret1"] = frame["close"].pct_change(fill_method=None).where(contiguous)
    oi_contiguous = contiguous & frame["oi"].notna() & frame["oi"].shift(1).notna()
    frame["oi_pct"] = frame["oi"].pct_change(fill_method=None).where(oi_contiguous)

    previous_close = frame["close"].shift(1)
    true_range = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous_close).abs(),
        (frame["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    true_range = true_range.where(contiguous, frame["high"] - frame["low"])

    price_segment = (~contiguous).cumsum()
    frame["atr14"] = true_range.groupby(price_segment).transform(
        lambda values: values.rolling(14, min_periods=14).mean()
    )
    frame["absret_q90"] = frame["ret1"].abs().groupby(price_segment).transform(
        lambda values: values.rolling(ROLLING_HOURS, min_periods=MIN_HISTORY_HOURS)
        .quantile(0.90).shift(1)
    )

    oi_segment = (~oi_contiguous).cumsum()
    positive_oi_change = frame["oi_pct"].clip(lower=0)
    for quantile, column in ((0.80, "oi_q80"), (0.90, "oi_q90")):
        frame[column] = positive_oi_change.groupby(oi_segment).transform(
            lambda values: values.rolling(ROLLING_HOURS, min_periods=MIN_HISTORY_HOURS)
            .quantile(quantile).shift(1)
        )
    return frame


def load_asset(ohlcv_dir: Path, derivatives_dir: Path, asset: str) -> pd.DataFrame:
    five_minute = pd.read_csv(Path(ohlcv_dir) / f"{asset}_5m.csv", parse_dates=["timestamp"])
    oi = pd.read_csv(Path(derivatives_dir) / f"{asset}_open_interest_1h.csv", parse_dates=["timestamp"])
    hourly = resample_complete_hours(five_minute)
    hourly["oi"] = align_oi_close_time(oi).reindex(hourly.index)
    return add_features(hourly)


def chronological_splits(length: int) -> dict[str, tuple[int, int]]:
    train_end = int(length * 0.60)
    validation_end = int(length * 0.80)
    return {
        "train": (0, train_end),
        "validation": (train_end, validation_end),
        "oos": (validation_end, length),
    }


def simulate(
    frame: pd.DataFrame,
    start: int,
    end: int,
    *,
    oi_quantile: float,
    stop_atr: float,
    target_r: float,
    cost_bps: float = 10.0,
    hold_hours: int = HOLD_HOURS,
) -> list[dict]:
    """Next-hour-open entry, ATR stop, fixed-R target, SL-first intrabar ambiguity."""
    oi_column = "oi_q80" if oi_quantile == 0.80 else "oi_q90"
    trades = []
    i = start
    while i < end - 1:
        signal = frame.iloc[i]
        required = (
            signal.get("ret1"), signal.get("absret_q90"), signal.get(oi_column),
            signal.get("oi_pct"), signal.get("atr14"),
        )
        if not all(np.isfinite(value) for value in required):
            i += 1
            continue
        if abs(signal.ret1) <= signal.absret_q90 or signal.oi_pct <= signal[oi_column] or signal.oi_pct <= 0:
            i += 1
            continue

        entry_index = i + 1
        if frame.index[entry_index] - frame.index[i] != pd.Timedelta(hours=1):
            i += 1
            continue
        last_index = entry_index + hold_hours - 1
        if last_index >= end:
            break
        future_index = frame.index[entry_index:last_index + 1]
        if len(future_index) != hold_hours or not all(
            gap == pd.Timedelta(hours=1)
            for gap in future_index[1:] - future_index[:-1]
        ):
            i = entry_index + 1
            continue

        direction = 1 if signal.ret1 > 0 else -1
        entry = float(frame.iloc[entry_index].open)
        risk_distance = float(signal.atr14) * stop_atr
        if not np.isfinite(entry) or entry <= 0 or not np.isfinite(risk_distance) or risk_distance <= 0:
            i += 1
            continue
        stop = entry - direction * risk_distance
        target = entry + direction * risk_distance * target_r
        exit_price = None
        outcome = None
        exit_index = None

        for j in range(entry_index, last_index + 1):
            bar = frame.iloc[j]
            op, high, low = float(bar.open), float(bar.high), float(bar.low)
            if direction == 1:
                if op <= stop:
                    exit_price, outcome = op, "SL"
                elif op >= target:
                    exit_price, outcome = op, "TP"
                elif low <= stop:
                    exit_price, outcome = stop, "SL"
                elif high >= target:
                    exit_price, outcome = target, "TP"
            else:
                if op >= stop:
                    exit_price, outcome = op, "SL"
                elif op <= target:
                    exit_price, outcome = op, "TP"
                elif high >= stop:
                    exit_price, outcome = stop, "SL"
                elif low <= target:
                    exit_price, outcome = target, "TP"
            if outcome:
                exit_index = j
                break

        if outcome is None:
            exit_index = last_index
            exit_price = float(frame.iloc[last_index].close)
            outcome = "TIME"
        gross_r = ((exit_price - entry) / risk_distance) * direction
        # All-in round-trip friction stress; funding is excluded pending event reconciliation.
        cost_r = (cost_bps / 10000.0) / (risk_distance / entry)
        trades.append({
            "signal_time": frame.index[i].isoformat(),
            "entry_time": frame.index[entry_index].isoformat(),
            "exit_time": frame.index[exit_index].isoformat(),
            "direction": "LONG" if direction == 1 else "SHORT",
            "outcome": outcome,
            "gross_R": gross_r,
            "net_R": gross_r - cost_r,
        })
        i = exit_index + 1  # one position per asset; no overlapping trades
    return trades


def summarize(trades: list[dict], days: float) -> dict:
    if not trades:
        return {
            "trades": 0, "win_rate_pct": None, "expectancy_R": None,
            "profit_factor": None, "max_drawdown_R": None,
            "max_losing_streak": 0, "trades_per_30d": 0.0,
        }
    returns = np.asarray([trade["net_R"] for trade in trades], dtype=float)
    positive = returns[returns > 0].sum()
    negative = -returns[returns < 0].sum()
    equity = np.cumsum(returns)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    drawdown = equity - peaks
    losing_streak = current_streak = 0
    for value in returns:
        current_streak = current_streak + 1 if value < 0 else 0
        losing_streak = max(losing_streak, current_streak)
    profit_factor = float(positive / negative) if negative > 0 else None
    return {
        "trades": len(trades),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
        "expectancy_R": round(float(returns.mean()), 4),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "max_drawdown_R": round(float(drawdown.min()), 4),
        "max_losing_streak": int(losing_streak),
        "trades_per_30d": round(float(len(trades) / days * 30), 2) if days > 0 else None,
    }


def run_screen(ohlcv_dir: Path, derivatives_dir: Path) -> list[dict]:
    results = []
    for asset in ASSETS:
        frame = load_asset(ohlcv_dir, derivatives_dir, asset)
        splits = chronological_splits(len(frame))
        for oi_quantile, stop_atr, target_r in itertools.product((0.80, 0.90), (1.0, 1.5), (2.0, 3.0)):
            row = {"asset": asset, "oi_quantile": oi_quantile, "stop_atr": stop_atr, "target_R": target_r}
            for split_name, (start, end) in splits.items():
                days = (
                    (frame.index[end - 1] - frame.index[start]).total_seconds() / 86400
                    if end - start > 1 else 0
                )
                for cost_bps in (10.0, 20.0):
                    trades = simulate(
                        frame, start, end, oi_quantile=oi_quantile,
                        stop_atr=stop_atr, target_r=target_r, cost_bps=cost_bps,
                    )
                    metrics = summarize(trades, days)
                    for key, value in metrics.items():
                        row[f"{split_name}_{int(cost_bps)}bps_{key}"] = value
            results.append(row)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohlcv-dir", type=Path, required=True)
    parser.add_argument("--derivatives-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("oi_expansion_results.json"))
    args = parser.parse_args()
    results = run_screen(args.ohlcv_dir, args.derivatives_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} asset/parameter rows to {args.output}")
    for asset in ASSETS:
        subset = [row for row in results if row["asset"] == asset]
        print(asset, "OOS 10bp expectancy range:",
              min(row["oos_10bps_expectancy_R"] for row in subset),
              max(row["oos_10bps_expectancy_R"] for row in subset))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
