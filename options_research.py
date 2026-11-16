"""Options research/backtest lab for Binance BTC/ETH options.

Historical option prints are sparse. This engine uses only traded contract candles,
never forward-fills quotes, enters after the underlying signal candle closes, and
flags/guards unobserved option-price gaps. It is a research proxy, not an exchange
account statement or evidence of executable fills.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class OptionsResearchError(ValueError):
    """Raised for malformed or insufficient options research inputs."""


@dataclass(frozen=True)
class ResearchConfig:
    interval: str = "1h"
    min_dte_days: int = 7
    max_dte_days: int = 90
    max_entry_delay_hours: float = 1.0
    stop_loss_pct: float = 0.30
    take_profit_pct: float = 0.50
    max_hold_hours: int = 4
    fee_bps_per_side: float = 5.0
    spread_bps_per_side: float = 25.0
    slippage_bps_per_side: float = 10.0
    gap_penalty_bps: float = 100.0
    initial_equity: float = 10_000.0
    risk_fraction: float = 0.01
    max_premium_notional_pct: float = 0.25
    min_qty: float = 0.01
    qty_step: float = 0.01

    def __post_init__(self):
        if self.interval not in {"1h"}:
            raise OptionsResearchError("This initial lab supports 1h options candles only; do not mix intervals.")
        if self.min_dte_days < 0 or self.max_dte_days <= self.min_dte_days:
            raise OptionsResearchError("DTE range must satisfy 0 <= min_dte_days < max_dte_days")
        if self.max_entry_delay_hours < 0 or self.max_hold_hours <= 0:
            raise OptionsResearchError("Entry delay must be non-negative and max hold must be positive")
        for name in ("stop_loss_pct", "take_profit_pct", "initial_equity", "risk_fraction",
                     "max_premium_notional_pct", "min_qty", "qty_step"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise OptionsResearchError(f"{name} must be finite and positive")
        if self.stop_loss_pct >= 1.0:
            raise OptionsResearchError("stop_loss_pct must be below 1.0 for a long option buyer")
        for name in ("fee_bps_per_side", "spread_bps_per_side", "slippage_bps_per_side", "gap_penalty_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0 or value >= 10_000:
                raise OptionsResearchError(f"{name} must be finite and in [0, 10000)")
        if not 0 < self.risk_fraction <= 0.10:
            raise OptionsResearchError("risk_fraction must be in (0, 0.10]")
        if not 0 < self.max_premium_notional_pct <= 1.0:
            raise OptionsResearchError("max_premium_notional_pct must be in (0, 1]")


SYMBOL_RE = re.compile(r"^(BTC|ETH)-(\d{6})-(\d+(?:\.\d+)?)-([CP])$")
OHLC = ["open", "high", "low", "close"]


def _utc_index(values: Any, label: str) -> pd.DatetimeIndex:
    try:
        idx = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    except Exception as exc:
        raise OptionsResearchError(f"{label} timestamps could not be parsed") from exc
    if idx.isna().any():
        raise OptionsResearchError(f"{label} contains invalid timestamps")
    return idx


def validate_ohlcv(frame: pd.DataFrame, label: str, *, allow_gaps: bool = True) -> pd.DataFrame:
    """Validate without sorting, deduplicating, forward-filling or repairing input data."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise OptionsResearchError(f"{label} data is empty")
    missing = set(OHLC).difference(frame.columns)
    if missing:
        raise OptionsResearchError(f"{label} is missing columns: {sorted(missing)}")
    out = frame.copy()
    out.index = _utc_index(out.index, label)
    out.index.name = "timestamp"
    if out.index.has_duplicates or not out.index.is_monotonic_increasing:
        raise OptionsResearchError(f"{label} timestamps must be unique and strictly chronological")
    if "volume" not in out:
        out["volume"] = 0.0
    for col in OHLC + ["volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    values = out[OHLC + ["volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise OptionsResearchError(f"{label} contains non-finite OHLCV values")
    if (out[OHLC] <= 0).any().any() or (out["volume"] < 0).any():
        raise OptionsResearchError(f"{label} prices must be positive and volume non-negative")
    invalid = ((out["high"] < out[["open", "close", "low"]].max(axis=1)) |
               (out["low"] > out[["open", "close", "high"]].min(axis=1)))
    if invalid.any():
        raise OptionsResearchError(f"{label} has {int(invalid.sum())} invalid OHLC candle(s)")
    if not allow_gaps:
        gaps = out.index.to_series().diff().dropna()
        if not gaps.eq(pd.Timedelta(hours=1)).all():
            raise OptionsResearchError(f"{label} must have contiguous hourly candles")
    return out[OHLC + ["volume"]]


def parse_option_symbol(symbol: str) -> dict[str, Any] | None:
    match = SYMBOL_RE.match(str(symbol).strip())
    if not match:
        return None
    asset, expiry_code, strike, side = match.groups()
    try:
        expiry_date = datetime.strptime(expiry_code, "%y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return {
        "asset": asset,
        "symbol": symbol,
        "expiry": pd.Timestamp(expiry_date),
        "strike": float(strike),
        "option_type": "CALL" if side == "C" else "PUT",
    }


def _read_time_indexed_csv(path: Path, label: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "open_time_utc" in frame:
        index = frame.pop("open_time_utc")
    elif "timestamp" in frame:
        index = frame.pop("timestamp")
    elif "open_time_ms" in frame:
        index = pd.to_datetime(pd.to_numeric(frame.pop("open_time_ms"), errors="coerce"), unit="ms", utc=True)
    elif len(frame.columns) and str(frame.columns[0]).lower() in {"timestamp", "time", "unnamed: 0"}:
        index = frame.pop(frame.columns[0])
    else:
        raise OptionsResearchError(f"{label} file {path} has no recognised timestamp column")
    frame.index = _utc_index(index, label)
    frame.index.name = "timestamp"
    if "trade_count" in frame:
        trades = pd.to_numeric(frame["trade_count"], errors="coerce").fillna(0)
        volume_source = frame["volume"] if "volume" in frame else pd.Series(0.0, index=frame.index)
        volume = pd.to_numeric(volume_source, errors="coerce").fillna(0)
        frame = frame[(trades > 0) & (volume > 0)]
    elif "volume" in frame:
        frame = frame[pd.to_numeric(frame["volume"], errors="coerce").fillna(0) > 0]
    return validate_ohlcv(frame, label, allow_gaps=True)


def load_underlying(data_dir: Path, asset: str) -> pd.DataFrame:
    candidates = [
        data_dir / "underlying" / f"{asset}_1h.csv",
        data_dir / "binance_options" / "underlying" / f"{asset}_1h.csv",
        data_dir / f"{asset}_1h.csv",
    ]
    for path in candidates:
        if path.exists():
            return validate_ohlcv(_read_time_indexed_csv(path, f"{asset} underlying"), f"{asset} underlying")
    raise OptionsResearchError(
        f"Missing {asset} hourly underlying history. Expected one of: " + ", ".join(map(str, candidates))
    )


def load_option_bars(data_dir: Path, asset: str) -> dict[str, dict[str, Any]]:
    folder = data_dir / "historical_klines_1h" / asset
    if not folder.exists():
        folder = data_dir / "binance_options" / "historical_klines_1h" / asset
    if not folder.exists():
        raise OptionsResearchError(f"Missing options candles folder: {folder}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.csv")):
        meta = parse_option_symbol(path.stem)
        if not meta or meta["asset"] != asset:
            continue
        try:
            bars = _read_time_indexed_csv(path, path.stem)
        except OptionsResearchError:
            continue
        if not bars.empty:
            result[path.stem] = {**meta, "bars": bars, "source_file": str(path)}
    if not result:
        raise OptionsResearchError(f"No usable traded option candle files found under {folder}")
    return result


def generate_signals(underlying: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Create five independent, close-confirmed hourly setups using past data only."""
    bars = validate_ohlcv(underlying, "underlying")
    o, h, l, c = (bars[k] for k in ("open", "high", "low", "close"))
    ema8 = c.ewm(span=8, adjust=False, min_periods=8).mean()
    ema20 = c.ewm(span=20, adjust=False, min_periods=20).mean()
    ema21 = c.ewm(span=21, adjust=False, min_periods=21).mean()
    ema50 = c.ewm(span=50, adjust=False, min_periods=50).mean()
    roc3 = c.pct_change(3)

    # Any strategy needs a contiguous 50-hour lookback; missing market bars invalidate that region.
    continuity = bars.index.to_series().diff().eq(pd.Timedelta(hours=1))
    continuity.iloc[0] = False
    valid_window = continuity.rolling(50, min_periods=50).sum().eq(50)

    def events(strategy_id: str, long_mask: pd.Series, short_mask: pd.Series, reason: str) -> pd.DataFrame:
        long_mask = long_mask.fillna(False) & valid_window
        short_mask = short_mask.fillna(False) & valid_window
        # Emit a setup only on its transition to true; avoid repeated entries during one trend state.
        long_event = long_mask & ~long_mask.shift(1, fill_value=False)
        short_event = short_mask & ~short_mask.shift(1, fill_value=False)
        rows = []
        for ts in bars.index[long_event]:
            rows.append({"signal_time": ts, "strategy_id": strategy_id, "direction": "LONG", "reason": reason})
        for ts in bars.index[short_event]:
            rows.append({"signal_time": ts, "strategy_id": strategy_id, "direction": "SHORT", "reason": reason})
        if not rows:
            return pd.DataFrame(columns=["strategy_id", "direction", "reason"], index=pd.DatetimeIndex([], name="signal_time"))
        out = pd.DataFrame(rows).set_index("signal_time").sort_index()
        return out

    momentum_long = (ema8 > ema21) & (roc3 >= 0.0025)
    momentum_short = (ema8 < ema21) & (roc3 <= -0.0025)
    opt01 = events("OPT-01_MOMENTUM", momentum_long, momentum_short, "EMA8/EMA21 alignment with 3-hour ROC confirmation")

    # Sweep of the prior 20-hour range followed by next-hour market-structure shift.
    prior_low = l.rolling(20, min_periods=20).min().shift(1)
    prior_high = h.rolling(20, min_periods=20).max().shift(1)
    bull_sweep = (l < prior_low) & (c > prior_low)
    bear_sweep = (h > prior_high) & (c < prior_high)
    bull_mss = bull_sweep.shift(1, fill_value=False) & (c > h.shift(1))
    bear_mss = bear_sweep.shift(1, fill_value=False) & (c < l.shift(1))
    opt02 = events("OPT-02_SWEEP_MSS", bull_mss, bear_mss, "20-hour liquidity sweep then next-hour close-confirmed MSS")

    ema_long = (ema20 > ema50) & (l <= ema20) & (c > ema20) & (c > o)
    ema_short = (ema20 < ema50) & (h >= ema20) & (c < ema20) & (c < o)
    opt03 = events("OPT-03_EMA_PULLBACK", ema_long, ema_short, "EMA20 pullback/reclaim aligned with EMA20/EMA50 trend")

    previous_close = c.shift(1)
    true_range = pd.concat([(h - l), (h - previous_close).abs(), (l - previous_close).abs()], axis=1).max(axis=1)
    atr12 = true_range.rolling(12, min_periods=12).mean()
    atr48 = true_range.rolling(48, min_periods=48).mean()
    compression = atr12 < (atr48 * 0.75)
    expansion_setup = compression & ~compression.shift(1, fill_value=False)
    opt04 = events("OPT-04_LONG_STRADDLE", expansion_setup, pd.Series(False, index=bars.index),
                   "new 12h-vs-48h realized-range compression; buy ATM call and put")
    opt05 = events("OPT-05_LONG_STRANGLE", expansion_setup, pd.Series(False, index=bars.index),
                   "new 12h-vs-48h realized-range compression; buy 2% OTM call and put")

    return {
        "OPT-01_MOMENTUM": opt01,
        "OPT-02_SWEEP_MSS": opt02,
        "OPT-03_EMA_PULLBACK": opt03,
        "OPT-04_LONG_STRADDLE": opt04,
        "OPT-05_LONG_STRANGLE": opt05,
    }


def _dte_ok(meta: dict[str, Any], signal_time: pd.Timestamp, cfg: ResearchConfig) -> bool:
    dte = (meta["expiry"] - signal_time).total_seconds() / 86400.0
    return cfg.min_dte_days <= dte <= cfg.max_dte_days


def _first_entry_row(bars: pd.DataFrame, earliest: pd.Timestamp, max_delay: pd.Timedelta) -> tuple[pd.Timestamp, pd.Series] | None:
    eligible = bars.index[(bars.index >= earliest) & (bars.index <= earliest + max_delay)]
    if len(eligible) == 0:
        return None
    ts = eligible[0]
    return ts, bars.loc[ts]


def _effective_cost_bps(cfg: ResearchConfig) -> float:
    return cfg.spread_bps_per_side + cfg.slippage_bps_per_side


def _round_qty_down(value: float, step: float) -> float:
    return math.floor((value + 1e-12) / step) * step


def _single_trade(
    signal_time: pd.Timestamp, signal: pd.Series, spot: float,
    contract: dict[str, Any], entry_time: pd.Timestamp, entry_bar: pd.Series,
    cfg: ResearchConfig, equity: float,
) -> tuple[dict[str, Any] | None, float]:
    bars = contract["bars"]
    entry_raw = float(entry_bar["open"])
    cost_rate = _effective_cost_bps(cfg) / 10_000.0
    fee_rate = cfg.fee_bps_per_side / 10_000.0
    entry_fill = entry_raw * (1.0 + cost_rate)
    stop = entry_fill * (1.0 - cfg.stop_loss_pct)
    target = entry_fill * (1.0 + cfg.take_profit_pct)
    # Size against stop-risk plus round-trip friction, capped by premium notional.
    estimated_risk_per_contract = (
        entry_fill * cfg.stop_loss_pct
        + entry_fill * cost_rate
        + stop * cost_rate
        + (entry_fill + stop) * fee_rate
    )
    risk_budget = equity * cfg.risk_fraction
    qty_by_risk = risk_budget / max(estimated_risk_per_contract, 1e-12)
    qty_by_notional = equity * cfg.max_premium_notional_pct / max(entry_fill, 1e-12)
    qty = _round_qty_down(min(qty_by_risk, qty_by_notional), cfg.qty_step)
    if qty < cfg.min_qty:
        return None, 0.0

    entry_fee = entry_fill * qty * fee_rate
    previous_time = entry_time
    exit_raw = None
    exit_time = None
    exit_reason = None
    gap_hours = 0.0
    same_bar_ambiguous = False
    held_hours = 0.0
    after_entry = bars.loc[bars.index >= entry_time]
    for ts, bar in after_entry.iterrows():
        if ts != entry_time:
            gap_hours = max(0.0, (ts - previous_time).total_seconds() / 3600.0 - 1.0)
        else:
            gap_hours = 0.0
        if gap_hours > 0:
            # Exit at the last actual traded close before the unobserved interval; do not invent stop/TP touches.
            prior = bars.loc[previous_time]
            exit_raw = float(prior["close"])
            exit_time = previous_time + pd.Timedelta(hours=1)
            exit_reason = "DATA_GAP_GUARD_EXIT"
            held_hours = max(0.0, (exit_time - entry_time).total_seconds() / 3600.0)
            break

        open_price, high, low = (float(bar[k]) for k in ("open", "high", "low"))
        if ts == entry_time:
            # Position is opened at this bar's open, so only the subsequent high/low path applies.
            stop_hit, target_hit = low <= stop, high >= target
            if stop_hit and target_hit:
                exit_raw, exit_reason, same_bar_ambiguous = stop, "SL_SAME_BAR_AMBIGUITY", True
            elif stop_hit:
                exit_raw, exit_reason = stop, "SL"
            elif target_hit:
                exit_raw, exit_reason = target, "TP"
        elif open_price <= stop:
            exit_raw, exit_reason = open_price, "SL_GAP"
        elif open_price >= target:
            exit_raw, exit_reason = target, "TP_GAP"
        else:
            stop_hit, target_hit = low <= stop, high >= target
            if stop_hit and target_hit:
                exit_raw, exit_reason, same_bar_ambiguous = stop, "SL_SAME_BAR_AMBIGUITY", True
            elif stop_hit:
                exit_raw, exit_reason = stop, "SL"
            elif target_hit:
                exit_raw, exit_reason = target, "TP"
        if exit_reason:
            exit_time = ts + pd.Timedelta(hours=1) if ts == entry_time else ts
            held_hours = (exit_time - entry_time).total_seconds() / 3600.0
            break
        bar_close = ts + pd.Timedelta(hours=1)
        held_hours = (bar_close - entry_time).total_seconds() / 3600.0
        if held_hours >= cfg.max_hold_hours:
            exit_raw, exit_time, exit_reason = float(bar["close"]), bar_close, "TIME_EXIT"
            break
        previous_time = ts

    if exit_raw is None:
        last_ts = bars.index[bars.index >= entry_time][-1]
        last_bar = bars.loc[last_ts]
        exit_raw, exit_time, exit_reason = float(last_bar["close"]), last_ts + pd.Timedelta(hours=1), "END_OF_DATA"
        held_hours = max(0.0, (exit_time - entry_time).total_seconds() / 3600.0)

    exit_cost_rate = cost_rate + (cfg.gap_penalty_bps / 10_000.0 if exit_reason == "DATA_GAP_GUARD_EXIT" else 0.0)
    exit_fill = max(0.0, float(exit_raw) * (1.0 - exit_cost_rate))
    exit_fee = exit_fill * qty * fee_rate
    pnl = (exit_fill - entry_fill) * qty - entry_fee - exit_fee
    actual_risk = max(1e-12, estimated_risk_per_contract * qty)
    net_r = pnl / actual_risk
    equity_after = equity + pnl
    meta = contract
    trade = {
        "strategy_id": signal["strategy_id"], "direction": signal["direction"],
        "signal_time": signal_time.isoformat(), "entry_time": entry_time.isoformat(),
        "exit_time": pd.Timestamp(exit_time).isoformat(), "option_symbol": meta["symbol"],
        "option_type": meta["option_type"], "strike": meta["strike"],
        "expiry": meta["expiry"].isoformat(), "spot_at_signal": float(spot),
        "entry_premium_raw": entry_raw, "entry_premium_fill": entry_fill,
        "exit_premium_raw": float(exit_raw), "exit_premium_fill": exit_fill,
        "quantity_contracts_model": qty, "premium_notional_model": entry_fill * qty,
        "gross_pnl_model": (float(exit_raw) - entry_raw) * qty,
        "net_pnl_model": pnl, "fees_model": entry_fee + exit_fee,
        "net_option_return_pct": (exit_fill - entry_fill) / entry_fill * 100.0,
        "net_r": net_r, "equity_before": equity, "equity_after": equity_after,
        "exit_reason": exit_reason, "held_hours": held_hours,
        "gap_hours_before_guard_exit": gap_hours,
        "same_bar_ambiguous": same_bar_ambiguous,
        "data_quality_flag": "GAP_GUARD_EXIT" if exit_reason == "DATA_GAP_GUARD_EXIT" else "TRADED_CANDLES_ONLY",
        "cost_assumptions_bps_per_side": {
            "fee": cfg.fee_bps_per_side, "spread_proxy": cfg.spread_bps_per_side,
            "slippage": cfg.slippage_bps_per_side,
        },
    }
    return trade, equity_after


def _select_single_contract(
    option_data: dict[str, dict[str, Any]], option_type: str,
    spot: float, signal_time: pd.Timestamp, entry_earliest: pd.Timestamp,
    cfg: ResearchConfig,
) -> tuple[dict[str, Any], pd.Timestamp, pd.Series] | None:
    candidates = []
    max_delay = pd.Timedelta(hours=cfg.max_entry_delay_hours)
    for contract in option_data.values():
        if contract["option_type"] != option_type or not _dte_ok(contract, signal_time, cfg):
            continue
        entry = _first_entry_row(contract["bars"], entry_earliest, max_delay)
        if entry is None:
            continue
        entry_time, entry_bar = entry
        distance = abs(contract["strike"] / spot - 1.0)
        candidates.append((distance, (contract["expiry"] - signal_time).total_seconds(), contract, entry_time, entry_bar))
    if not candidates:
        return None
    _, _, contract, entry_time, entry_bar = min(candidates, key=lambda x: (x[0], x[1]))
    return contract, entry_time, entry_bar


def _run_single_leg(
    asset: str, strategy_id: str, signals: pd.DataFrame,
    underlying: pd.DataFrame, option_data: dict[str, dict[str, Any]], cfg: ResearchConfig,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    equity = cfg.initial_equity
    busy_until = pd.Timestamp.min.tz_localize("UTC")
    for signal_time, signal in signals.iterrows():
        if signal_time < busy_until:
            continue
        spot = float(underlying.loc[signal_time, "close"])
        desired_type = "CALL" if signal["direction"] == "LONG" else "PUT"
        entry_earliest = signal_time + pd.Timedelta(hours=1)
        selected = _select_single_contract(option_data, desired_type, spot, signal_time, entry_earliest, cfg)
        if selected is None:
            continue
        contract, entry_time, entry_bar = selected
        trade, equity = _single_trade(signal_time, signal, spot, contract, entry_time, entry_bar, cfg, equity)
        if trade:
            trade["asset"] = asset
            trade["signal_delay_hours"] = (entry_time - entry_earliest).total_seconds() / 3600.0
            trades.append(trade)
            busy_until = pd.Timestamp(trade["exit_time"])
    return trades


def _pair_contracts(
    option_data: dict[str, dict[str, Any]], spot: float, signal_time: pd.Timestamp,
    entry_earliest: pd.Timestamp, cfg: ResearchConfig, strangle: bool,
) -> tuple[dict[str, Any], dict[str, Any], pd.Timestamp] | None:
    calls = [x for x in option_data.values() if x["option_type"] == "CALL" and _dte_ok(x, signal_time, cfg)]
    puts = [x for x in option_data.values() if x["option_type"] == "PUT" and _dte_ok(x, signal_time, cfg)]
    max_delay = pd.Timedelta(hours=cfg.max_entry_delay_hours)
    pairs = []
    for call in calls:
        for put in puts:
            if call["expiry"] != put["expiry"]:
                continue
            if strangle:
                if call["strike"] < spot * 1.02 or put["strike"] > spot * 0.98:
                    continue
                strike_distance = abs(call["strike"] / (spot * 1.02) - 1.0) + abs(put["strike"] / (spot * 0.98) - 1.0)
            else:
                if call["strike"] != put["strike"]:
                    continue
                strike_distance = abs(call["strike"] / spot - 1.0)
            common = call["bars"].index.intersection(put["bars"].index)
            common = common[(common >= entry_earliest) & (common <= entry_earliest + max_delay)]
            if len(common) == 0:
                continue
            entry_time = common[0]
            dte = (call["expiry"] - signal_time).total_seconds()
            pairs.append((strike_distance, dte, call, put, entry_time))
    if not pairs:
        return None
    _, _, call, put, entry_time = min(pairs, key=lambda x: (x[0], x[1]))
    return call, put, entry_time


def _run_pair_strategy(
    asset: str, strategy_id: str, signals: pd.DataFrame, underlying: pd.DataFrame,
    option_data: dict[str, dict[str, Any]], cfg: ResearchConfig, strangle: bool,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    equity = cfg.initial_equity
    busy_until = pd.Timestamp.min.tz_localize("UTC")
    for signal_time, signal in signals.iterrows():
        if signal_time < busy_until:
            continue
        spot = float(underlying.loc[signal_time, "close"])
        entry_earliest = signal_time + pd.Timedelta(hours=1)
        pair = _pair_contracts(option_data, spot, signal_time, entry_earliest, cfg, strangle)
        if pair is None:
            continue
        call, put, entry_time = pair
        cb, pb = call["bars"].loc[entry_time], put["bars"].loc[entry_time]
        entry_raw = float(cb["open"]) + float(pb["open"])
        if entry_raw <= 0:
            continue
        cost_rate = _effective_cost_bps(cfg) / 10_000.0
        fee_rate = cfg.fee_bps_per_side / 10_000.0
        entry_fill = entry_raw * (1 + cost_rate)
        # Long straddle/strangle is premium-risk: max loss is the whole debit.
        estimated_risk_per_unit = entry_fill + entry_fill * cost_rate + entry_fill * 2 * fee_rate
        risk_budget = equity * cfg.risk_fraction
        qty_risk = risk_budget / max(estimated_risk_per_unit, 1e-12)
        qty_notional = equity * cfg.max_premium_notional_pct / entry_fill
        qty = _round_qty_down(min(qty_risk, qty_notional), cfg.qty_step)
        if qty < cfg.min_qty:
            continue
        entry_fee = entry_fill * qty * fee_rate

        common = call["bars"].index.intersection(put["bars"].index)
        future = common[common > entry_time]
        exit_time = None
        exit_raw = None
        exit_reason = None
        held_hours = 0.0
        previous = entry_time
        gap_hours = 0.0
        target_time = entry_time + pd.Timedelta(hours=cfg.max_hold_hours)
        for ts in future:
            current_gap = max(0.0, (ts - previous).total_seconds() / 3600.0 - 1.0)
            if current_gap > 0:
                pc, pp = call["bars"].loc[previous], put["bars"].loc[previous]
                exit_raw = float(pc["close"]) + float(pp["close"])
                exit_time = previous + pd.Timedelta(hours=1)
                exit_reason = "DATA_GAP_GUARD_EXIT"
                gap_hours = current_gap
                held_hours = (exit_time - entry_time).total_seconds() / 3600.0
                break
            if ts + pd.Timedelta(hours=1) >= target_time:
                ec, ep = call["bars"].loc[ts], put["bars"].loc[ts]
                exit_raw = float(ec["close"]) + float(ep["close"])
                exit_time = ts + pd.Timedelta(hours=1)
                exit_reason = "TIME_EXIT"
                held_hours = (exit_time - entry_time).total_seconds() / 3600.0
                break
            previous = ts
        if exit_raw is None:
            if len(future):
                last_common = future[-1]
                ec, ep = call["bars"].loc[last_common], put["bars"].loc[last_common]
                exit_raw = float(ec["close"]) + float(ep["close"])
                exit_time = last_common + pd.Timedelta(hours=1)
                exit_reason = "END_OF_DATA"
                held_hours = (exit_time - entry_time).total_seconds() / 3600.0
            else:
                continue
        exit_cost = cost_rate + (cfg.gap_penalty_bps / 10_000.0 if exit_reason == "DATA_GAP_GUARD_EXIT" else 0.0)
        exit_fill = max(0.0, float(exit_raw) * (1 - exit_cost))
        exit_fee = exit_fill * qty * fee_rate
        pnl = (exit_fill - entry_fill) * qty - entry_fee - exit_fee
        actual_risk = max(1e-12, estimated_risk_per_unit * qty)
        net_r = pnl / actual_risk
        equity_after = equity + pnl
        trade = {
            "asset": asset, "strategy_id": strategy_id, "direction": "LONG_VOLATILITY",
            "signal_time": signal_time.isoformat(), "entry_time": entry_time.isoformat(),
            "exit_time": pd.Timestamp(exit_time).isoformat(), "option_symbol": f"{call['symbol']} + {put['symbol']}",
            "option_type": "STRANGLE" if strangle else "STRADDLE",
            "strike": f"{call['strike']} / {put['strike']}", "expiry": call["expiry"].isoformat(),
            "spot_at_signal": spot, "entry_premium_raw": entry_raw, "entry_premium_fill": entry_fill,
            "exit_premium_raw": float(exit_raw), "exit_premium_fill": exit_fill,
            "quantity_contracts_model": qty, "premium_notional_model": entry_fill * qty,
            "gross_pnl_model": (float(exit_raw) - entry_raw) * qty,
            "net_pnl_model": pnl, "fees_model": entry_fee + exit_fee,
            "net_option_return_pct": (exit_fill - entry_fill) / entry_fill * 100.0,
            "net_r": net_r, "equity_before": equity, "equity_after": equity_after,
            "exit_reason": exit_reason, "held_hours": held_hours,
            "gap_hours_before_guard_exit": gap_hours,
            "same_bar_ambiguous": False,
            "data_quality_flag": "GAP_GUARD_EXIT" if exit_reason == "DATA_GAP_GUARD_EXIT" else "TRADED_CANDLES_ONLY",
            "cost_assumptions_bps_per_side": {
                "fee": cfg.fee_bps_per_side, "spread_proxy": cfg.spread_bps_per_side,
                "slippage": cfg.slippage_bps_per_side,
            },
        }
        trades.append(trade)
        equity = equity_after
        busy_until = pd.Timestamp(exit_time)
    return trades


def _max_streak(values: list[bool], target: bool) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value is target else 0
        best = max(best, current)
    return best


def calculate_metrics(trades: pd.DataFrame, initial_equity: float) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None,
            "net_pnl_model": 0.0, "return_on_initial_equity_pct": 0.0,
            "average_net_option_return_pct": None, "expectancy_r": None,
            "profit_factor": None, "max_drawdown_pct": 0.0,
            "max_consecutive_losses": 0, "average_hold_hours": None,
            "gap_guard_exits": 0, "same_bar_ambiguous_exits": 0,
            "status": "NO_TRADES_IN_AVAILABLE_DATA",
        }
    pnl = pd.to_numeric(trades["net_pnl_model"], errors="coerce").fillna(0.0)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    # Rebuild equity from this segment's own PnL so train/validation/test metrics
    # each start from the same declared initial capital (no cross-segment leakage).
    equity = [float(initial_equity)]
    for pnl_value in pnl:
        equity.append(equity[-1] + float(pnl_value))
    curve = pd.Series(equity, dtype=float)
    dd = curve / curve.cummax() - 1.0
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "trades": int(len(trades)), "wins": int(len(wins)), "losses": int(len(losses)),
        "win_rate_pct": round(100.0 * len(wins) / len(trades), 4),
        "net_pnl_model": round(float(pnl.sum()), 8),
        "return_on_initial_equity_pct": round(100.0 * float(pnl.sum()) / initial_equity, 6),
        "average_net_option_return_pct": round(float(trades["net_option_return_pct"].mean()), 6),
        "expectancy_r": round(float(trades["net_r"].mean()), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else None,
        "max_drawdown_pct": round(float(dd.min() * 100.0), 6),
        "max_consecutive_losses": _max_streak([bool(x < 0) for x in pnl], True),
        "average_hold_hours": round(float(trades["held_hours"].mean()), 4),
        "gap_guard_exits": int((trades["exit_reason"] == "DATA_GAP_GUARD_EXIT").sum()),
        "same_bar_ambiguous_exits": int(trades["same_bar_ambiguous"].fillna(False).astype(bool).sum()),
        "ending_equity_model": round(float(curve.iloc[-1]), 8),
        "status": "INDICATIVE" if (trades["data_quality_flag"] == "GAP_GUARD_EXIT").any() else "TRADED_CANDLE_REPLAY",
    }


def _segment_boundaries(index: pd.DatetimeIndex) -> dict[str, pd.Timestamp]:
    """60/20/20 chronological split with one hourly bar purged at each boundary."""
    n = len(index)
    train_end_i = max(0, min(n - 1, int(n * 0.60) - 1))
    validation_end_i = max(train_end_i, min(n - 1, int(n * 0.80) - 1))
    validation_start_i = min(n - 1, train_end_i + 2)
    test_start_i = min(n - 1, validation_end_i + 2)
    return {
        "train_end": index[train_end_i],
        "validation_start": index[validation_start_i],
        "validation_end": index[validation_end_i],
        "test_start": index[test_start_i],
    }


def _monthly_summary(trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    frame = trades.copy()
    frame["month"] = pd.to_datetime(frame["exit_time"], utc=True).dt.strftime("%Y-%m")
    out = []
    for month, group in frame.groupby("month", sort=True):
        out.append({"month": month, "trades": int(len(group)),
                    "net_pnl_model": round(float(group["net_pnl_model"].sum()), 8),
                    "win_rate_pct": round(100.0 * float((group["net_pnl_model"] > 0).mean()), 4)})
    return out



def _coverage_summary(option_data: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    coverage = []
    for symbol, contract in sorted(option_data.items()):
        bars = contract["bars"]
        elapsed_hours = max(1.0, (bars.index[-1] - bars.index[0]).total_seconds() / 3600.0 + 1.0)
        gaps = bars.index.to_series().diff().dropna().dt.total_seconds() / 3600.0
        coverage.append({
            "symbol": symbol,
            "traded_hour_bars": int(len(bars)),
            "first_trade_bar_utc": bars.index[0].isoformat(),
            "last_trade_bar_utc": bars.index[-1].isoformat(),
            "observed_trade_hour_pct": round(100.0 * len(bars) / elapsed_hours, 4),
            "median_gap_hours": round(float(gaps.median()), 4) if not gaps.empty else None,
            "max_gap_hours": round(float(gaps.max()), 4) if not gaps.empty else None,
        })
    return coverage


def run_asset_research(asset: str, data_dir: Path, out_dir: Path, cfg: ResearchConfig) -> dict[str, Any]:
    underlying = load_underlying(data_dir, asset)
    option_data = load_option_bars(data_dir, asset)
    signal_sets = generate_signals(underlying)
    boundaries = _segment_boundaries(underlying.index)
    strategy_trades: dict[str, list[dict[str, Any]]] = {}

    for strategy_id, signals in signal_sets.items():
        if strategy_id == "OPT-04_LONG_STRADDLE":
            trades = _run_pair_strategy(asset, strategy_id, signals, underlying, option_data, cfg, strangle=False)
        elif strategy_id == "OPT-05_LONG_STRANGLE":
            trades = _run_pair_strategy(asset, strategy_id, signals, underlying, option_data, cfg, strangle=True)
        else:
            trades = _run_single_leg(asset, strategy_id, signals, underlying, option_data, cfg)
        for trade in trades:
            ts = pd.Timestamp(trade["signal_time"])
            if ts <= boundaries["train_end"]:
                trade["split"] = "train"
            elif boundaries["validation_start"] <= ts <= boundaries["validation_end"]:
                trade["split"] = "validation"
            elif ts >= boundaries["test_start"]:
                trade["split"] = "test"
            else:
                trade["split"] = "purged_boundary_bar"
        strategy_trades[strategy_id] = trades

    from options_selling import run_credit_spread_research
    selling_result = run_credit_spread_research(asset, underlying, option_data, signal_sets, cfg)
    selling_trades_path = out_dir / f"{asset.lower()}_options_selling_trades.csv"
    selling_trades = selling_result["trades"]
    selling_trades.to_csv(selling_trades_path, index=False)

    all_trades = [trade for rows in strategy_trades.values() for trade in rows]
    out_dir.mkdir(parents=True, exist_ok=True)
    all_frame = pd.DataFrame(all_trades)
    if not all_frame.empty:
        all_frame = all_frame.sort_values(["signal_time", "strategy_id"]).reset_index(drop=True)
    trades_path = out_dir / f"{asset.lower()}_options_trades.csv"
    all_frame.to_csv(trades_path, index=False)

    results = {}
    for strategy_id, rows in strategy_trades.items():
        frame = pd.DataFrame(rows)
        results[strategy_id] = {
            "all": calculate_metrics(frame, cfg.initial_equity),
            "train": calculate_metrics(frame[frame["split"] == "train"], cfg.initial_equity) if not frame.empty else calculate_metrics(frame, cfg.initial_equity),
            "validation": calculate_metrics(frame[frame["split"] == "validation"], cfg.initial_equity) if not frame.empty else calculate_metrics(frame, cfg.initial_equity),
            "test": calculate_metrics(frame[frame["split"] == "test"], cfg.initial_equity) if not frame.empty else calculate_metrics(frame, cfg.initial_equity),
            "monthly": _monthly_summary(frame),
            "signals_generated": int(len(signal_sets[strategy_id])),
        }
    report = {
        "asset": asset, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_interval": cfg.interval, "underlying_bars": int(len(underlying)),
        "underlying_start": underlying.index[0].isoformat(), "underlying_end": underlying.index[-1].isoformat(),
        "option_contract_files": int(len(option_data)),
        "option_contracts": sorted(option_data.keys()),
        "option_data_coverage": _coverage_summary(option_data),
        "chronological_split": {k: v.isoformat() for k, v in boundaries.items()},
        "oos_reliability": "LOW_HISTORY" if len(underlying) < 500 else "RESEARCH_SAMPLE_ONLY",
        "config": asdict(cfg),
        "execution_model": {
            "entry": "next traded option candle open after signal close; maximum delay enforced",
            "single_leg_exit": "premium-price stop/target; same-candle stop-first; fixed max holding time",
            "pair_exit": "first common traded call/put candle close after fixed holding horizon",
            "no_trade_bars": "excluded; never forward-filled",
            "unobserved_gaps": "guard exit at last observed traded close plus extra gap penalty; flagged, not treated as ordinary fill",
            "costs": "configurable per-side fee plus spread proxy and slippage",
            "limitations": [
                "No historical bid/ask quotes or order-book depth; spread is a configurable proxy.",
                "No historical Greeks/IV/OI series before prospective snapshots began.",
                "No contract multiplier, exercise/settlement, margin, liquidation or exchange account accounting.",
                "Option candles may be sparse. Gap-guard exits are indicative, not verified executable fills.",
                "This initial release tests 1h signals and 1h option candles only.",
            ],
        },
        "strategies": results,
        "selling_strategies": selling_result["strategies"],
        "selling_execution_model": selling_result["execution_model"],
        "selling_trades_csv": str(selling_trades_path),
        "promotion_status": "RESEARCH_ONLY_NOT_APPROVED",
        "trades_csv": str(trades_path),
    }
    report_path = out_dir / f"{asset.lower()}_options_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BTC/ETH Binance options strategy research backtests")
    parser.add_argument("--data-dir", type=Path, default=Path("market_data/binance_options"),
                        help="Options collector data root, or market_data root")
    parser.add_argument("--out-dir", type=Path, default=Path("research/options"))
    parser.add_argument("--asset", choices=["BTC", "ETH", "both"], default="both")
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=90)
    parser.add_argument("--stop-pct", type=float, default=0.30)
    parser.add_argument("--target-pct", type=float, default=0.50)
    parser.add_argument("--max-hold-hours", type=int, default=4)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--spread-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=10.0)
    args = parser.parse_args()
    cfg = ResearchConfig(min_dte_days=args.min_dte, max_dte_days=args.max_dte,
                         stop_loss_pct=args.stop_pct, take_profit_pct=args.target_pct,
                         max_hold_hours=args.max_hold_hours, fee_bps_per_side=args.fee_bps,
                         spread_bps_per_side=args.spread_bps, slippage_bps_per_side=args.slippage_bps)
    assets = ["BTC", "ETH"] if args.asset == "both" else [args.asset]
    summaries = []
    for asset in assets:
        report = run_asset_research(asset, args.data_dir, args.out_dir, cfg)
        summaries.append({"asset": asset, "report": str(args.out_dir / f"{asset.lower()}_options_report.json"),
                          "strategies": {k: v["all"] for k, v in report["strategies"].items()}})
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
