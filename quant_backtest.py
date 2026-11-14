"""Deterministic, OHLCV-driven event replay for research signals.

This is a price-unit/R-multiple simulator, not an exchange-contract emulator.
It includes explicit taker-fee and slippage assumptions but excludes funding,
spread/depth, contract multipliers, margin/liquidation and settlement conversion.
Never interpret its equity column as a broker/exchange account statement.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class BacktestError(ValueError):
    """Raised when input data or simulation settings are unsafe to replay."""


@dataclass(frozen=True)
class BacktestConfig:
    timeframe_seconds: int
    fee_bps_per_side: float
    slippage_bps_per_side: float
    initial_capital: float = 100_000.0
    risk_fraction: float = 0.01
    max_leverage: float = 1.0
    gap_policy: str = "close_at_next_open"

    def __post_init__(self):
        if type(self.timeframe_seconds) is not int or self.timeframe_seconds <= 0:
            raise BacktestError("timeframe_seconds must be a positive integer")
        for name in ("fee_bps_per_side", "slippage_bps_per_side",
                     "initial_capital", "risk_fraction", "max_leverage"):
            value = getattr(self, name)
            if not math.isfinite(float(value)) or float(value) < 0:
                raise BacktestError(f"{name} must be finite and non-negative")
        if self.initial_capital <= 0:
            raise BacktestError("initial_capital must be positive")
        if not 0 < self.risk_fraction <= 0.10:
            raise BacktestError("risk_fraction must be in (0, 0.10]")
        if self.max_leverage <= 0:
            raise BacktestError("max_leverage must be positive")
        if self.gap_policy != "close_at_next_open":
            raise BacktestError("Only conservative gap_policy='close_at_next_open' is supported")
        if self.fee_bps_per_side >= 10_000 or self.slippage_bps_per_side >= 10_000:
            raise BacktestError("fee and slippage must each be below 10,000 bps")


def _utc_index(index: pd.Index, label: str) -> pd.DatetimeIndex:
    try:
        result = pd.DatetimeIndex(pd.to_datetime(index, utc=True))
    except Exception as exc:
        raise BacktestError(f"{label} index must contain valid timestamps") from exc
    if result.isna().any():
        raise BacktestError(f"{label} index contains NaT")
    return result


def validate_ohlcv(frame: pd.DataFrame, timeframe_seconds: int) -> pd.DataFrame:
    """Validate, but never silently sort, deduplicate, fill or repair, OHLCV input."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise BacktestError("OHLCV input must be a non-empty DataFrame")
    required = {"open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise BacktestError(f"OHLCV input is missing columns: {sorted(missing)}")
    out = frame.copy()
    out.index = _utc_index(out.index, "OHLCV")
    out.index.name = "timestamp"
    if out.index.has_duplicates:
        raise BacktestError("OHLCV timestamps must be unique")
    if not out.index.is_monotonic_increasing:
        raise BacktestError("OHLCV timestamps must already be strictly chronological")
    if "volume" not in out:
        out["volume"] = 0.0
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    values = out[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise BacktestError("OHLCV contains non-finite values")
    if (out[["open", "high", "low", "close"]] <= 0).any().any():
        raise BacktestError("OHLC prices must be positive")
    invalid = (
        (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise BacktestError(f"OHLC invariants fail on {int(invalid.sum())} row(s)")
    if (out["volume"] < 0).any():
        raise BacktestError("Volume cannot be negative")
    deltas = out.index.to_series().diff().dropna().dt.total_seconds()
    if (deltas < timeframe_seconds).any():
        raise BacktestError("OHLCV has overlapping or sub-timeframe timestamps")
    return out[["open", "high", "low", "close", "volume"]]


def validate_signals(signals: pd.DataFrame, bar_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Signals are known only at their own bar close and fill no earlier than next bar open."""
    if signals is None:
        empty = pd.DataFrame(index=bar_index, columns=["side", "stop_price", "target_price"])
        empty["side"] = 0
        empty["stop_price"] = np.nan
        empty["target_price"] = np.nan
        return empty
    if not isinstance(signals, pd.DataFrame):
        raise BacktestError("signals must be a DataFrame")
    required = {"side", "stop_price", "target_price"}
    missing = required.difference(signals.columns)
    if missing:
        raise BacktestError(f"signals are missing columns: {sorted(missing)}")
    out = signals.copy()
    out.index = _utc_index(out.index, "signals")
    out.index.name = "timestamp"
    if out.index.has_duplicates:
        raise BacktestError("Signal timestamps must be unique")
    unknown = out.index.difference(bar_index)
    if len(unknown):
        raise BacktestError("Every signal timestamp must match an OHLCV bar")
    out["side"] = pd.to_numeric(out["side"], errors="coerce")
    if out["side"].isna().any() or not out["side"].isin([-1, 0, 1]).all():
        raise BacktestError("signal side must be exactly -1 (short), 0 (none), or 1 (long)")
    for col in ("stop_price", "target_price"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    active = out["side"] != 0
    if (out.loc[active, ["stop_price", "target_price"]].isna().any().any()
            or not np.isfinite(out.loc[active, ["stop_price", "target_price"]].to_numpy(dtype=float)).all()):
        raise BacktestError("Active signals require finite stop_price and target_price")
    if (out.loc[active, ["stop_price", "target_price"]] <= 0).any().any():
        raise BacktestError("Active signal stop and target prices must be positive")
    aligned = pd.DataFrame(index=bar_index, columns=["side", "stop_price", "target_price"])
    aligned["side"] = 0
    aligned["stop_price"] = np.nan
    aligned["target_price"] = np.nan
    aligned.loc[out.index, ["side", "stop_price", "target_price"]] = out[
        ["side", "stop_price", "target_price"]
    ]
    aligned["side"] = aligned["side"].astype(int)
    return aligned


def _adverse_fill(raw_price: float, action: int, slippage_bps: float) -> float:
    """action=+1 is a buy; action=-1 is a sell."""
    slip = slippage_bps / 10_000.0
    return float(raw_price * (1.0 + action * slip))


def _exit_candidate(position: dict[str, Any], row: pd.Series,
                    slippage_bps: float) -> tuple[float, str, bool] | None:
    side = int(position["side"])
    stop = float(position["stop_price"])
    target = float(position["target_price"])
    open_price, high, low = (float(row[k]) for k in ("open", "high", "low"))
    if side == 1:
        stop_hit = low <= stop
        target_hit = high >= target
        stop_raw = min(open_price, stop) if open_price <= stop else stop
        target_raw = target
        # The opening print is the first known price in the bar. If it gaps
        # through a resting target, that target was reached before any later
        # intrabar move; do not misclassify a subsequent stop touch as ambiguous.
        if open_price <= stop:
            return _adverse_fill(stop_raw, -side, slippage_bps), "SL_GAP", False
        if open_price >= target:
            return _adverse_fill(target_raw, -side, slippage_bps), "TP_GAP", False
    else:
        stop_hit = high >= stop
        target_hit = low <= target
        stop_raw = max(open_price, stop) if open_price >= stop else stop
        target_raw = target
        if open_price >= stop:
            return _adverse_fill(stop_raw, -side, slippage_bps), "SL_GAP", False
        if open_price <= target:
            return _adverse_fill(target_raw, -side, slippage_bps), "TP_GAP", False
    if stop_hit and target_hit:
        # OHLC does not reveal which level was first: resolve against the strategy.
        return _adverse_fill(stop_raw, -side, slippage_bps), "SL_SAME_BAR_AMBIGUITY", True
    if stop_hit:
        return _adverse_fill(stop_raw, -side, slippage_bps), "SL", False
    if target_hit:
        # Target is treated as a resting limit filled at the target, with no price improvement.
        return _adverse_fill(target_raw, -side, slippage_bps), "TP", False
    return None


def _max_streak(outcomes: list[bool], target: bool) -> int:
    best = current = 0
    for outcome in outcomes:
        current = current + 1 if outcome is target else 0
        best = max(best, current)
    return best


def _performance_metrics(trades: pd.DataFrame, equity: pd.DataFrame,
                         config: BacktestConfig, gap_count: int,
                         missing_intervals: int, skipped_entries: int,
                         ambiguous_bars: int) -> dict[str, Any]:
    if trades.empty:
        wins = losses = 0
        net_r = gross_profit = gross_loss = total_fees_r = total_slippage_r = 0.0
        win_rate = avg_r = expectancy = 0.0
        pf = None
        outcomes: list[bool] = []
    else:
        values = trades["net_r"].astype(float)
        wins = int((values > 0).sum())
        losses = int((values < 0).sum())
        net_r = float(values.sum())
        gross_profit = float(trades.loc[values > 0, "net_pnl_cash"].sum())
        gross_loss = float(-trades.loc[values < 0, "net_pnl_cash"].sum())
        total_fees_r = float(trades["fees_r"].sum())
        total_slippage_r = float(trades["slippage_r"].sum())
        win_rate = 100.0 * wins / len(trades)
        avg_r = float(values.mean())
        expectancy = avg_r
        pf = gross_profit / gross_loss if gross_loss > 0 else None
        outcomes = [bool(v > 0) for v in values]
    if equity.empty:
        max_dd = 0.0
        ending_equity = config.initial_capital
    else:
        curve = equity["equity"].astype(float)
        peaks = curve.cummax()
        drawdown = (curve / peaks) - 1.0
        max_dd = float(drawdown.min() * 100.0)
        ending_equity = float(curve.iloc[-1])
    return {
        "total_trades": int(len(trades)),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 4),
        "positive_net_pnl_cash_units": round(gross_profit, 8),
        "negative_net_pnl_cash_units": round(gross_loss, 8),
        "net_profit_r_sum": round(net_r, 8),
        "average_r_per_trade": round(avg_r, 8),
        "expectancy_r_per_trade": round(expectancy, 8),
        "profit_factor": round(pf, 8) if pf is not None else None,
        "max_drawdown_pct_realized_equity": round(max_dd, 6),
        "ending_equity_cash_units": round(ending_equity, 8),
        "max_consecutive_wins": _max_streak(outcomes, True),
        "max_consecutive_losses": _max_streak(outcomes, False),
        "fees_paid_r": round(total_fees_r, 8),
        "slippage_cost_r": round(total_slippage_r, 8),
        "data_gap_events": int(gap_count),
        "missing_intervals_observed": int(missing_intervals),
        "gap_forced_exits": int((trades["exit_reason"] == "DATA_GAP").sum()) if not trades.empty else 0,
        "skipped_entries": int(skipped_entries),
        "same_bar_ambiguous_exits": int(ambiguous_bars),
        "funding_included": False,
        "spread_and_depth_included": False,
        "contract_multiplier_and_settlement_included": False,
        "margin_and_liquidation_included": False,
        "cost_model_status": "PARTIAL_FEES_AND_SLIPPAGE_ONLY",
        "pnl_unit_warning": (
            "Cash/equity values are price-unit linear-model estimates, not Delta account PnL. "
            "Funding, bid/ask spread, depth/impact, contract multipliers, margin, liquidation "
            "and settlement conversion are not modelled."
        ),
        "assumptions": asdict(config),
    }


def run_backtest(ohlcv: pd.DataFrame, signals: pd.DataFrame,
                 config: BacktestConfig) -> dict[str, Any]:
    """Replay one non-overlapping strategy stream with next-bar entries and conservative fills."""
    bars = validate_ohlcv(ohlcv, config.timeframe_seconds)
    sig = validate_signals(signals, bars.index)
    fee_rate = config.fee_bps_per_side / 10_000.0
    slip_bps = config.slippage_bps_per_side
    position: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    gap_events = missing_intervals = skipped_entries = ambiguous_bars = 0
    equity = float(config.initial_capital)

    def close_position(ts, raw_exit, exit_fill, reason, ambiguous=False):
        nonlocal position, equity, ambiguous_bars
        assert position is not None
        side = int(position["side"])
        entry = float(position["entry_fill"])
        stop = float(position["stop_price"])
        risk_per_unit = abs(entry - stop)
        gross_per_unit = side * (float(exit_fill) - entry)
        fee_per_unit = fee_rate * (abs(entry) + abs(float(exit_fill)))
        net_per_unit = gross_per_unit - fee_per_unit
        quantity = float(position["quantity_units"])
        gross_cash = gross_per_unit * quantity
        fee_cash = fee_per_unit * quantity
        net_cash = net_per_unit * quantity
        risk_cash = risk_per_unit * quantity
        slippage_per_unit = (
            abs(float(position["entry_raw"]) - float(position["entry_fill"]))
            + abs(float(raw_exit) - float(exit_fill))
        )
        slip_cash = slippage_per_unit * quantity
        net_r = net_cash / risk_cash if risk_cash else 0.0
        before = equity
        equity = max(0.0, equity + net_cash)
        if ambiguous:
            ambiguous_bars += 1
        trades.append({
            "signal_time": position["signal_time"],
            "entry_time": position["entry_time"],
            "exit_time": ts,
            "side": "LONG" if side == 1 else "SHORT",
            "entry_price_raw": position["entry_raw"],
            "entry_price_fill": entry,
            "stop_price": stop,
            "target_price": position["target_price"],
            "exit_price_raw": float(raw_exit),
            "exit_price_fill": float(exit_fill),
            "exit_reason": reason,
            "quantity_price_units": quantity,
            "gross_pnl_cash_units": gross_cash,
            "fees_cash_units": fee_cash,
            "net_pnl_cash": net_cash,
            "risk_cash_units": risk_cash,
            "gross_r": gross_cash / risk_cash if risk_cash else 0.0,
            "fees_r": fee_cash / risk_cash if risk_cash else 0.0,
            "slippage_r": slip_cash / risk_cash if risk_cash else 0.0,
            "net_r": net_r,
            "equity_before": before,
            "equity_after": equity,
            "same_bar_ambiguous": bool(ambiguous),
        })
        position = None

    for i, (ts, row) in enumerate(bars.iterrows()):
        # Missing bars are never synthesized. Cancel pending entries and conservatively
        # close an open position at the first observed bar after the gap.
        if i > 0:
            elapsed = (ts - bars.index[i - 1]).total_seconds()
            if elapsed > config.timeframe_seconds:
                gap_events += 1
                missing = max(1, int(round(elapsed / config.timeframe_seconds)) - 1)
                missing_intervals += missing
                if pending is not None:
                    skipped_entries += 1
                    pending = None
                if position is not None:
                    raw = float(row["open"])
                    fill = _adverse_fill(raw, -int(position["side"]), slip_bps)
                    close_position(ts, raw, fill, "DATA_GAP")

        # A signal from the prior bar is entered at this bar's open, never at signal close.
        if pending is not None and position is None:
            side = int(pending["side"])
            raw_open = float(row["open"])
            stop = float(pending["stop_price"])
            target = float(pending["target_price"])
            valid_open = (stop < raw_open < target) if side == 1 else (target < raw_open < stop)
            if valid_open and equity > 0:
                entry_fill = _adverse_fill(raw_open, side, slip_bps)
                valid_fill = (stop < entry_fill < target) if side == 1 else (target < entry_fill < stop)
                if valid_fill:
                    risk_per_unit = abs(entry_fill - stop)
                    risk_cash = equity * config.risk_fraction
                    quantity = risk_cash / risk_per_unit
                    max_quantity = equity * config.max_leverage / entry_fill
                    quantity = min(quantity, max_quantity)
                    if quantity > 0 and math.isfinite(quantity):
                        position = {
                            "side": side,
                            "signal_time": pending["signal_time"],
                            "entry_time": ts,
                            "entry_raw": raw_open,
                            "entry_fill": entry_fill,
                            "stop_price": stop,
                            "target_price": target,
                            "quantity_units": quantity,
                        }
                    else:
                        skipped_entries += 1
                else:
                    skipped_entries += 1
            else:
                skipped_entries += 1
            pending = None

        # Test stop/target on the entry bar too. When both lie inside the same OHLC
        # range, stop wins because the intrabar path is unknowable.
        if position is not None:
            candidate = _exit_candidate(position, row, slip_bps)
            if candidate is not None:
                exit_fill, reason, ambiguous = candidate
                raw_exit = min(float(row["open"]), float(position["stop_price"])) if reason.startswith("SL") and position["side"] == 1 and float(row["open"]) <= float(position["stop_price"]) else (
                    max(float(row["open"]), float(position["stop_price"])) if reason.startswith("SL") and position["side"] == -1 and float(row["open"]) >= float(position["stop_price"]) else (
                        float(position["stop_price"]) if reason.startswith("SL") else float(position["target_price"])
                    )
                )
                close_position(ts, raw_exit, exit_fill, reason, ambiguous)

        # A close-confirmed signal schedules an entry for the next available bar only.
        if position is None and equity > 0:
            signal = sig.iloc[i]
            side = int(signal["side"])
            if side != 0:
                if i == len(bars) - 1:
                    # No following bar exists, so a close-confirmed signal cannot be filled.
                    skipped_entries += 1
                else:
                    close_price = float(row["close"])
                    stop = float(signal["stop_price"])
                    target = float(signal["target_price"])
                    valid_levels = (stop < close_price < target) if side == 1 else (target < close_price < stop)
                    if valid_levels:
                        pending = {
                            "side": side, "signal_time": ts,
                            "stop_price": stop, "target_price": target,
                        }
                    else:
                        skipped_entries += 1

        equity_rows.append({
            "timestamp": ts,
            "equity": equity,
            "position_open": position is not None,
            "data_gap_before_bar": bool(i > 0 and (ts - bars.index[i - 1]).total_seconds() > config.timeframe_seconds),
        })

    # A remaining position is marked out at the final observed close, not left invisibly open.
    if position is not None:
        ts = bars.index[-1]
        raw = float(bars.iloc[-1]["close"])
        fill = _adverse_fill(raw, -int(position["side"]), slip_bps)
        close_position(ts, raw, fill, "END_OF_DATA")
        equity_rows[-1]["equity"] = equity
        equity_rows[-1]["position_open"] = False
    if pending is not None:
        skipped_entries += 1

    trade_frame = pd.DataFrame(trades)
    equity_frame = pd.DataFrame(equity_rows).set_index("timestamp")
    if not trade_frame.empty:
        trade_frame["signal_time"] = pd.to_datetime(trade_frame["signal_time"], utc=True)
        trade_frame["entry_time"] = pd.to_datetime(trade_frame["entry_time"], utc=True)
        trade_frame["exit_time"] = pd.to_datetime(trade_frame["exit_time"], utc=True)
    metrics = _performance_metrics(
        trade_frame, equity_frame, config, gap_events, missing_intervals,
        skipped_entries, ambiguous_bars,
    )
    return {
        "trades": trade_frame,
        "equity_curve": equity_frame,
        "metrics": metrics,
        "data_gaps": _gap_report(bars, config.timeframe_seconds),
    }


def _gap_report(bars: pd.DataFrame, timeframe_seconds: int) -> pd.DataFrame:
    rows = []
    for i in range(1, len(bars)):
        elapsed = (bars.index[i] - bars.index[i - 1]).total_seconds()
        if elapsed > timeframe_seconds:
            rows.append({
                "previous_timestamp": bars.index[i - 1],
                "next_timestamp": bars.index[i],
                "elapsed_seconds": elapsed,
                "missing_intervals_estimate": max(1, int(round(elapsed / timeframe_seconds)) - 1),
            })
    return pd.DataFrame(rows, columns=[
        "previous_timestamp", "next_timestamp", "elapsed_seconds",
        "missing_intervals_estimate",
    ])


def chronological_splits(frame: pd.DataFrame, train_fraction: float = 0.60,
                         validation_fraction: float = 0.20,
                         test_fraction: float = 0.20, purge_bars: int = 0,
                         embargo_bars: int = 0) -> dict[str, pd.DataFrame]:
    """Create chronological train/validation/test slices with boundary purge and embargo."""
    fractions = (train_fraction, validation_fraction, test_fraction)
    if any(not math.isfinite(float(x)) or x <= 0 for x in fractions):
        raise BacktestError("split fractions must be finite and positive")
    if not math.isclose(sum(fractions), 1.0, rel_tol=0, abs_tol=1e-9):
        raise BacktestError("train, validation and test fractions must sum to 1")
    if type(purge_bars) is not int or purge_bars < 0:
        raise BacktestError("purge_bars must be a non-negative integer")
    if type(embargo_bars) is not int or embargo_bars < 0:
        raise BacktestError("embargo_bars must be a non-negative integer")
    n = len(frame)
    first = int(n * train_fraction)
    second = int(n * (train_fraction + validation_fraction))
    train_end = first - purge_bars
    validation_start = first + embargo_bars
    validation_end = second - purge_bars
    test_start = second + embargo_bars
    if train_end <= 0 or validation_end <= validation_start or test_start >= n:
        raise BacktestError("Not enough rows for requested splits, purge and embargo")
    return {
        "train": frame.iloc[:train_end].copy(),
        "validation": frame.iloc[validation_start:validation_end].copy(),
        "test": frame.iloc[test_start:].copy(),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay close-confirmed research signals on OHLCV bars.")
    parser.add_argument("--ohlcv", required=True, help="CSV with timestamp,open,high,low,close[,volume].")
    parser.add_argument("--signals", required=True, help="CSV with timestamp,side,stop_price,target_price.")
    parser.add_argument("--timeframe-seconds", required=True, type=int)
    parser.add_argument("--fee-bps-per-side", required=True, type=float,
                        help="Explicit taker fee assumption in basis points per side.")
    parser.add_argument("--slippage-bps-per-side", required=True, type=float,
                        help="Explicit adverse slippage assumption in basis points per side.")
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--max-leverage", type=float, default=1.0)
    parser.add_argument("--output-dir", default="backtest_output")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bars = pd.read_csv(args.ohlcv, parse_dates=["timestamp"]).set_index("timestamp")
        signals = pd.read_csv(args.signals, parse_dates=["timestamp"]).set_index("timestamp")
        config = BacktestConfig(
            timeframe_seconds=args.timeframe_seconds,
            fee_bps_per_side=args.fee_bps_per_side,
            slippage_bps_per_side=args.slippage_bps_per_side,
            initial_capital=args.initial_capital,
            risk_fraction=args.risk_fraction,
            max_leverage=args.max_leverage,
        )
        result = run_backtest(bars, signals, config)
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        result["trades"].to_csv(output / "trades.csv", index=False)
        result["equity_curve"].to_csv(output / "equity_curve.csv")
        result["data_gaps"].to_csv(output / "data_gaps.csv", index=False)
        _write_json(output / "summary.json", result["metrics"])
        print(json.dumps(result["metrics"], indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (BacktestError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Backtest failed closed: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
