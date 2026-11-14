#!/usr/bin/env python3
"""BTCUSD VWAP trend-continuation study; experimental, no live use.

Signals use completed 1H/4H and 15m context plus a completed 5m trigger.
Entry is the next 5m open. UTC-day VWAP uses Delta traded-price candle volume,
which is exchange-specific rather than consolidated market-wide volume.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=5)
MAX_HOLD = 48                    # 4 hours
COSTS = (6, 12, 20)              # assumed round-trip bps, one BTC leg
BANDS = (0.10, 0.20)             # VWAP proximity in 5m ATR
CONFIRMATIONS = ("reclaim_close", "break_prior_extreme")
VOLUME_FILTERS = (0.0, 1.0, 1.5) # current volume / prior-20-bar median
STOPS = ("signal_extreme", "atr1", "atr1p5")
TARGETS = (1.5, 2.0, 3.0)
SESSIONS = ("all", "07-13", "13-19")
HTF4_FILTERS = (False, True)
MIN_TRAIN, MIN_VALIDATION = 40, 20
MAX_SHORTLIST = 25


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_ohlcv(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    if d.timestamp.duplicated().any():
        raise ValueError("duplicate BTC timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    required = ["open", "high", "low", "close", "volume"]
    if any(c not in d.columns for c in required):
        raise ValueError(f"missing required OHLCV columns: {required}")
    for c in required:
        d[c] = pd.to_numeric(d[c], errors="raise")
    values = d[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("non-finite OHLCV values")
    if (d[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("non-positive OHLC")
    if (d.volume < 0).any():
        raise ValueError("negative volume")
    bad = (
        (d.high < d[["open", "close", "low"]].max(axis=1))
        | (d.low > d[["open", "close", "high"]].min(axis=1))
    )
    if bad.any():
        raise ValueError(f"invalid OHLC rows: {int(bad.sum())}")
    if d.empty:
        raise ValueError("empty BTC dataset")
    return d


def rma(values: pd.Series, length: int) -> pd.Series:
    a = values.to_numpy(float)
    out = np.full(len(a), np.nan)
    if len(a) >= length and np.isfinite(a[:length]).all():
        out[length - 1] = float(a[:length].mean())
        for i in range(length, len(a)):
            if np.isfinite(a[i]):
                out[i] = (out[i - 1] * (length - 1) + a[i]) / length
    return pd.Series(out, index=values.index)


def aggregate_segmented(d: pd.DataFrame, rule: str, expected: int) -> pd.DataFrame:
    """Aggregate only complete bars inside a single contiguous 5m segment."""
    frames = []
    cols = ["open", "high", "low", "close", "volume"]
    for seg, g in d.groupby("segment", sort=False):
        rs = g[cols].resample(rule, label="right", closed="left")
        x = rs.agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        })
        count = g.close.resample(rule, label="right", closed="left").count()
        x = x.loc[count.eq(expected)].dropna(subset=["open", "high", "low", "close"])
        if not x.empty:
            x["segment"] = int(seg)
            frames.append(x)
    if not frames:
        return pd.DataFrame(columns=cols + ["segment"], index=pd.DatetimeIndex([], tz="UTC"))
    out = pd.concat(frames).sort_index()
    out.index.name = "available_time"
    return out


def attach_context(base: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    """As-of join context only at/after its completed-bar availability time."""
    if context.empty:
        return base.copy()
    left = base.reset_index().rename(columns={base.index.name or "index": "timestamp"})
    right = context.copy()
    right.index.name = "available_time"
    right = right.reset_index()
    left = left.sort_values("timestamp")
    right = right.sort_values("available_time")
    merged = pd.merge_asof(
        left, right, left_on="timestamp", right_on="available_time",
        by="segment", direction="backward", allow_exact_matches=True,
    )
    merged = merged.drop(columns=["available_time"])
    return merged.set_index("timestamp").sort_index()


def prepare_features(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    d = raw.copy().sort_index()
    diffs = d.index.to_series().diff()
    d["segment"] = diffs.ne(BAR).cumsum().astype(int)

    d["atr5"] = np.nan
    d["vol_median20"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        prev = g.close.shift(1)
        tr = pd.concat([
            g.high - g.low, (g.high - prev).abs(), (g.low - prev).abs()
        ], axis=1).max(axis=1)
        d.loc[g.index, "atr5"] = rma(tr, 14).to_numpy()
        d.loc[g.index, "vol_median20"] = (
            g.volume.rolling(20, min_periods=20).median().shift(1).to_numpy()
        )

    # Completed 15m bars; UTC-day VWAP is reset at each UTC day and data segment.
    m15 = aggregate_segmented(d, "15min", 3)
    if m15.empty:
        raise ValueError("no complete 15m bars")
    m15["utc_day"] = (m15.index - pd.Timedelta(minutes=15)).normalize()
    typical = (m15.high + m15.low + m15.close) / 3.0
    group_keys = [m15.segment, m15.utc_day]
    cum_vol = m15.volume.groupby(group_keys).cumsum()
    cum_pv = (typical * m15.volume).groupby(group_keys).cumsum()
    cum_p2v = (typical.pow(2) * m15.volume).groupby(group_keys).cumsum()
    m15["vwap15"] = cum_pv / cum_vol.replace(0, np.nan)
    variance = (cum_p2v / cum_vol.replace(0, np.nan) - m15.vwap15.pow(2)).clip(lower=0)
    m15["vwap_sd15"] = np.sqrt(variance)
    m15["vwap_slope4"] = m15.groupby(group_keys, sort=False).vwap15.diff(4)
    ctx15 = m15[["segment", "close", "vwap15", "vwap_slope4", "utc_day"]].rename(
        columns={"close": "close15", "utc_day": "vwap_day"}
    )

    # Completed 1h EMA50/EMA200 regime, reset at each data gap.
    h1 = aggregate_segmented(d, "1h", 12)
    if h1.empty:
        raise ValueError("no complete 1h bars")
    h1["ema50_1h"] = np.nan
    h1["ema200_1h"] = np.nan
    for _, g in h1.groupby("segment", sort=False):
        h1.loc[g.index, "ema50_1h"] = g.close.ewm(
            span=50, adjust=False, min_periods=50
        ).mean().to_numpy()
        h1.loc[g.index, "ema200_1h"] = g.close.ewm(
            span=200, adjust=False, min_periods=200
        ).mean().to_numpy()
    h1["trend1h"] = np.select(
        [
            (h1.close > h1.ema50_1h) & (h1.ema50_1h > h1.ema200_1h),
            (h1.close < h1.ema50_1h) & (h1.ema50_1h < h1.ema200_1h),
        ],
        ["bull", "bear"], default="unavailable",
    )
    ctx1h = h1[["segment", "close", "ema50_1h", "ema200_1h", "trend1h"]].rename(
        columns={"close": "close1h"}
    )

    # Optional completed 4h EMA50 slope confirmation.
    h4 = aggregate_segmented(d, "4h", 48)
    if h4.empty:
        raise ValueError("no complete 4h bars")
    h4["ema50_4h"] = np.nan
    for _, g in h4.groupby("segment", sort=False):
        h4.loc[g.index, "ema50_4h"] = g.close.ewm(
            span=50, adjust=False, min_periods=50
        ).mean().to_numpy()
    h4["ema50_slope3_4h"] = h4.groupby("segment", sort=False).ema50_4h.diff(3)
    ctx4h = h4[["segment", "ema50_4h", "ema50_slope3_4h"]]

    out = attach_context(d, ctx15)
    out = attach_context(out, ctx1h)
    out = attach_context(out, ctx4h)

    quality = {
        "rows": int(len(d)),
        "first_5m_open_utc": d.index.min().isoformat(),
        "last_5m_open_utc": d.index.max().isoformat(),
        "gap_count": int(d.segment.nunique() - 1),
        "zero_volume_bars": int((d.volume == 0).sum()),
        "negative_volume_bars": int((d.volume < 0).sum()),
        "complete_15m_bars": int(len(m15)),
        "complete_1h_bars": int(len(h1)),
        "complete_4h_bars": int(len(h4)),
        "segments": int(d.segment.nunique()),
        "volume_note": "Delta exchange-specific traded-price candle volume; not consolidated market-wide volume.",
    }
    return out, quality


def session_ok(ts: pd.Timestamp, session: str) -> bool:
    if session == "all":
        return True
    if session == "07-13":
        return 7 <= ts.hour < 13
    if session == "13-19":
        return 13 <= ts.hour < 19
    raise ValueError(f"unknown session {session}")


def build_signals(d: pd.DataFrame, band: float, confirmation: str,
                  volume_mult: float, use_4h_slope: bool) -> list[dict]:
    o, h, l, c, v = (d[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume"))
    atr = d.atr5.to_numpy(float)
    vwap = d.vwap15.to_numpy(float)
    slope = d.vwap_slope4.to_numpy(float)
    close15 = d.close15.to_numpy(float)
    close1h = d.close1h.to_numpy(float)
    ema50 = d.ema50_1h.to_numpy(float)
    ema200 = d.ema200_1h.to_numpy(float)
    slope4h = d.ema50_slope3_4h.to_numpy(float)
    median_vol = d.vol_median20.to_numpy(float)
    segment = d.segment.to_numpy(int)

    prev_c = np.roll(c, 1)
    prev_h = np.roll(h, 1)
    prev_l = np.roll(l, 1)
    prev_vwap = np.roll(vwap, 1)
    vwap_day = d.vwap_day.to_numpy()
    prev_vwap_day = np.roll(vwap_day, 1)
    same_vwap_day = vwap_day == prev_vwap_day
    prev_segment = np.roll(segment, 1)
    prev_c[0] = prev_h[0] = prev_l[0] = prev_vwap[0] = np.nan
    prev_segment[0] = -1

    valid = (
        np.isfinite(atr) & (atr > 0) & np.isfinite(vwap)
        & np.isfinite(slope) & np.isfinite(close15)
        & np.isfinite(close1h) & np.isfinite(ema50) & np.isfinite(ema200)
        & (segment == prev_segment) & same_vwap_day
    )
    touch = (l <= vwap + band * atr) & (h >= vwap - band * atr)
    long_trend = valid & (close1h > ema50) & (ema50 > ema200)
    short_trend = valid & (close1h < ema50) & (ema50 < ema200)
    long_context = (close15 > vwap) & (slope > 0)
    short_context = (close15 < vwap) & (slope < 0)
    if use_4h_slope:
        long_trend &= np.isfinite(slope4h) & (slope4h > 0)
        short_trend &= np.isfinite(slope4h) & (slope4h < 0)

    if confirmation == "reclaim_close":
        long_confirm = (c > vwap) & (prev_c <= prev_vwap)
        short_confirm = (c < vwap) & (prev_c >= prev_vwap)
    elif confirmation == "break_prior_extreme":
        long_confirm = (c > prev_h) & (c > vwap)
        short_confirm = (c < prev_l) & (c < vwap)
    else:
        raise ValueError(f"unknown confirmation {confirmation}")

    volume_ok = np.ones(len(d), dtype=bool)
    if volume_mult > 0:
        volume_ok = (
            np.isfinite(median_vol) & (median_vol > 0)
            & (v >= volume_mult * median_vol)
        )

    long_mask = long_trend & long_context & touch & long_confirm & volume_ok
    short_mask = short_trend & short_context & touch & short_confirm & volume_ok
    indices = np.flatnonzero(long_mask | short_mask)
    out = []
    for i in indices:
        side = 1 if long_mask[i] else -1
        out.append({
            "signal_i": int(i),
            "side": int(side),
            "regime": "bull" if side == 1 else "bear",
        })
    return out


def stop_target(side: int, entry: float, signal_high: float, signal_low: float,
                signal_atr: float, stop_mode: str, target_r: float):
    if stop_mode == "signal_extreme":
        stop = signal_low if side == 1 else signal_high
    elif stop_mode == "atr1":
        stop = entry - signal_atr if side == 1 else entry + signal_atr
    elif stop_mode == "atr1p5":
        stop = entry - 1.5 * signal_atr if side == 1 else entry + 1.5 * signal_atr
    else:
        raise ValueError(f"unknown stop mode {stop_mode}")
    risk = entry - stop if side == 1 else stop - entry
    if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
        return None, None, None
    target = entry + target_r * risk if side == 1 else entry - target_r * risk
    return stop, target, risk


def exit_fill(side: int, o: float, h: float, l: float, stop: float, target: float):
    """Conservative intrabar ordering: stop before target; adverse stop gaps."""
    if side == 1:
        if o <= stop:
            return min(o, stop), "SL"
        if l <= stop:
            return stop, "SL"
        if h >= target:
            return target, "TP"
    else:
        if o >= stop:
            return max(o, stop), "SL"
        if h >= stop:
            return stop, "SL"
        if l <= target:
            return target, "TP"
    return None, None


def simulate(d: pd.DataFrame, signals: list[dict], cfg: dict,
             start_i: int, end_i: int, cost_bps: int) -> pd.DataFrame:
    o, h, l, c = (d[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    atr = d.atr5.to_numpy(float)
    segment = d.segment.to_numpy(int)
    rows = []
    last_exit = start_i - 1
    for sig in signals:
        si = sig["signal_i"]
        entry_i = si + 1
        if si < start_i or entry_i <= last_exit or entry_i >= end_i:
            continue
        if entry_i + MAX_HOLD > end_i:
            continue
        if not np.all(segment[si:entry_i + MAX_HOLD] == segment[si]):
            continue
        if not session_ok(d.index[entry_i], cfg["session"]):
            continue
        side = int(sig["side"])
        entry = float(o[entry_i])
        signal_atr = float(atr[si])
        stop, target, risk = stop_target(
            side, entry, float(h[si]), float(l[si]), signal_atr,
            cfg["stop"], float(cfg["target_r"]),
        )
        if stop is None:
            continue
        # A market entry that opens through its intended stop is invalid.
        if (side == 1 and entry <= stop) or (side == -1 and entry >= stop):
            continue

        outcome, exit_i, exit_price = "TIME", entry_i + MAX_HOLD - 1, float(c[entry_i + MAX_HOLD - 1])
        for j in range(entry_i, entry_i + MAX_HOLD):
            fill, why = exit_fill(side, float(o[j]), float(h[j]), float(l[j]), stop, target)
            if why:
                outcome, exit_i, exit_price = why, j, float(fill)
                break
        gross_r = (exit_price - entry) / risk if side == 1 else (entry - exit_price) / risk
        cost_r = (cost_bps / 10000.0) / (risk / entry)
        rows.append({
            "signal_time": d.index[si] + BAR,
            "entry_time": d.index[entry_i],
            "exit_time": d.index[exit_i] + BAR,
            "side": "long" if side == 1 else "short",
            "regime": sig["regime"],
            "entry": entry, "stop": stop, "target": target, "exit": exit_price,
            "risk_points": risk, "outcome": outcome,
            "gross_R": gross_r, "cost_R": cost_r, "net_R": gross_r - cost_r,
            "cost_bps_round_trip": cost_bps,
            "hold_bars": exit_i - entry_i + 1,
            **{k: v for k, v in cfg.items() if k != "signals"},
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def metrics(t: pd.DataFrame) -> dict:
    if t.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": None,
            "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "positive_month_fraction": 0.0,
            "positive_months": 0, "months": 0, "TP": 0, "SL": 0, "TIME": 0,
        }
    x = t.sort_values("entry_time")
    r = x.net_R.to_numpy(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = np.r_[0.0, np.cumsum(r)]
    dd = eq - np.maximum.accumulate(eq)
    streak = maximum = 0
    for value in r:
        streak = streak + 1 if value < 0 else 0
        maximum = max(maximum, streak)
    monthly = x.assign(month=x.exit_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(x)),
        "win_rate_pct": float((r > 0).mean() * 100),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and -losses.sum() > 0 else None,
        "net_R": float(r.sum()),
        "avg_R": float(r.mean()),
        "max_drawdown_R": float(dd.min()),
        "max_losing_streak": int(maximum),
        "positive_month_fraction": float((monthly > 0).mean()) if len(monthly) else 0.0,
        "positive_months": int((monthly > 0).sum()),
        "months": int(len(monthly)),
        "TP": int((x.outcome == "TP").sum()),
        "SL": int((x.outcome == "SL").sum()),
        "TIME": int((x.outcome == "TIME").sum()),
    }


def summarize_diagnostics(trades: pd.DataFrame, label: str, monthly_rows: list, regime_rows: list):
    if trades.empty:
        return
    x = trades.copy()
    x["month"] = x.exit_time.dt.strftime("%Y-%m")
    for month, g in x.groupby("month"):
        monthly_rows.append({
            "candidate": label, "split": str(g.split.iloc[0]),
            "month": month, "trades": len(g), "net_R": float(g.net_R.sum()),
            "avg_R": float(g.net_R.mean()),
        })
    for regime, g in x.groupby("regime"):
        regime_rows.append({
            "candidate": label, "split": str(g.split.iloc[0]),
            "regime": regime, "trades": len(g), "net_R": float(g.net_R.sum()),
            "avg_R": float(g.net_R.mean()),
        })


def run(price_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = load_ohlcv(price_path)
    d, quality = prepare_features(raw)
    n = len(d)
    a, b = int(n * 0.70), int(n * 0.85)
    if a < 1 or b <= a or b >= n:
        raise ValueError("insufficient rows for chronological 70/15/15 split")
    bounds = {"train": (0, a), "validation": (a, b), "oos": (b, n)}

    configs = []
    signal_cache = {}
    for band, confirmation, volume_mult, stop, target, session, use4 in itertools.product(
        BANDS, CONFIRMATIONS, VOLUME_FILTERS, STOPS, TARGETS, SESSIONS, HTF4_FILTERS
    ):
        key = (band, confirmation, volume_mult, use4)
        if key not in signal_cache:
            signal_cache[key] = build_signals(d, band, confirmation, volume_mult, use4)
        cfg = {
            "band_atr": band, "confirmation": confirmation,
            "volume_mult": volume_mult, "stop": stop, "target_r": target,
            "session": session, "four_hour_slope_filter": use4,
        }
        configs.append((cfg, signal_cache[key]))

    matrix = []
    candidate_trades = {}
    for cfg, signals in configs:
        train = simulate(d, signals, cfg, *bounds["train"], 12)
        validation = simulate(d, signals, cfg, *bounds["validation"], 12)
        mt, mv = metrics(train), metrics(validation)
        row = dict(cfg)
        row.update({f"train_{k}": v for k, v in mt.items()})
        row.update({f"validation_{k}": v for k, v in mv.items()})
        train_gate = (
            mt["trades"] >= MIN_TRAIN and mt["profit_factor"] is not None
            and mt["profit_factor"] >= 1.05 and mt["net_R"] > 0
            and mt["max_drawdown_R"] >= -20.0
            and mt["positive_month_fraction"] >= 0.50
        )
        row["train_gate"] = bool(train_gate)
        matrix.append(row)
        if train_gate:
            cfg_key = (float(cfg["band_atr"]), str(cfg["confirmation"]),
                       float(cfg["volume_mult"]), str(cfg["stop"]),
                       float(cfg["target_r"]), str(cfg["session"]),
                       bool(cfg["four_hour_slope_filter"]))
            candidate_trades[cfg_key] = (cfg, signals, train, validation, mt, mv)

    md = pd.DataFrame(matrix)
    md.to_csv(out_dir / "matrix.csv", index=False)
    eligible = md[md.train_gate].copy()
    if not eligible.empty:
        eligible["quality"] = eligible.train_net_R / eligible.train_max_drawdown_R.abs().clip(lower=1.0)
        shortlist = eligible.sort_values(["quality", "train_trades"], ascending=[False, False]).head(MAX_SHORTLIST)
        validation_pass_ids = []
        for _, row in shortlist.iterrows():
            key_cfg = {k: row[k] for k in (
                "band_atr", "confirmation", "volume_mult", "stop", "target_r",
                "session", "four_hour_slope_filter"
            )}
            key = (float(key_cfg["band_atr"]), str(key_cfg["confirmation"]),
                   float(key_cfg["volume_mult"]), str(key_cfg["stop"]),
                   float(key_cfg["target_r"]), str(key_cfg["session"]),
                   bool(key_cfg["four_hour_slope_filter"]))
            cfg, signals, train, validation, mt, mv = candidate_trades[key]
            validation_gate = (
                mv["trades"] >= MIN_VALIDATION and mv["profit_factor"] is not None
                and mv["profit_factor"] >= 1.05 and mv["net_R"] > 0
                and mv["max_drawdown_R"] >= -12.0
                and mv["positive_month_fraction"] >= 0.50
            )
            if validation_gate:
                validation_pass_ids.append((key, mv))
            md.loc[
                (md.band_atr == row.band_atr)
                & (md.confirmation == row.confirmation)
                & (md.volume_mult == row.volume_mult)
                & (md.stop == row.stop)
                & (md.target_r == row.target_r)
                & (md.session == row.session)
                & (md.four_hour_slope_filter == row.four_hour_slope_filter),
                "validation_gate",
            ] = bool(validation_gate)
    else:
        shortlist = pd.DataFrame()
        validation_pass_ids = []
    md.to_csv(out_dir / "matrix.csv", index=False)

    # Keep transparent diagnostics for the strongest training candidate and
    # strongest validation candidate with >=20 trades, even if they fail gates.
    all_cfg_rows = md.copy()
    top_train_row = all_cfg_rows.sort_values("train_net_R", ascending=False).iloc[0]
    top_val_pool = all_cfg_rows[all_cfg_rows.validation_trades >= MIN_VALIDATION]
    top_val_row = (
        top_val_pool.sort_values("validation_net_R", ascending=False).iloc[0]
        if not top_val_pool.empty else None
    )
    monthly_rows, regime_rows, diagnostic_trade_frames = [], [], []
    for label, row, split_name in (
        ("best_train_net", top_train_row, "train"),
        ("best_validation_net_min20", top_val_row, "validation"),
    ):
        if row is None:
            continue
        cfg = {
            "band_atr": row.band_atr, "confirmation": row.confirmation,
            "volume_mult": row.volume_mult, "stop": row.stop,
            "target_r": row.target_r, "session": row.session,
            "four_hour_slope_filter": bool(row.four_hour_slope_filter),
        }
        signals = build_signals(d, cfg["band_atr"], cfg["confirmation"],
                                cfg["volume_mult"], cfg["four_hour_slope_filter"])
        trades = simulate(d, signals, cfg, *bounds[split_name], 12)
        if not trades.empty:
            trades["split"] = split_name
            trades["candidate"] = label
            diagnostic_trade_frames.append(trades)
            summarize_diagnostics(trades, label, monthly_rows, regime_rows)
    if diagnostic_trade_frames:
        pd.concat(diagnostic_trade_frames, ignore_index=True).to_csv(
            out_dir / "diagnostic_trades_12bp.csv", index=False
        )
    pd.DataFrame(monthly_rows).to_csv(out_dir / "diagnostic_monthly.csv", index=False)
    pd.DataFrame(regime_rows).to_csv(out_dir / "diagnostic_regimes.csv", index=False)

    # Cost sensitivity for train-eligible candidates; OOS only for a single
    # candidate that independently passes the preregistered validation gate.
    cost_rows = []
    for _, row in eligible.head(MAX_SHORTLIST).iterrows():
        cfg = {
            "band_atr": row.band_atr, "confirmation": row.confirmation,
            "volume_mult": row.volume_mult, "stop": row.stop,
            "target_r": row.target_r, "session": row.session,
            "four_hour_slope_filter": bool(row.four_hour_slope_filter),
        }
        signals = build_signals(d, cfg["band_atr"], cfg["confirmation"],
                                cfg["volume_mult"], cfg["four_hour_slope_filter"])
        for split_name in ("train", "validation"):
            for cost in COSTS:
                t = simulate(d, signals, cfg, *bounds[split_name], cost)
                cost_rows.append({
                    **cfg, "split": split_name, "cost_bps": cost, **metrics(t)
                })

    selected_config = None
    oos_summary = {}
    oos_evaluated = bool(validation_pass_ids)
    if validation_pass_ids:
        selected_key, selected_val_metrics = sorted(
            validation_pass_ids,
            key=lambda item: (
                item[1]["net_R"] / max(abs(item[1]["max_drawdown_R"]), 1.0),
                item[1]["trades"],
            ),
            reverse=True,
        )[0]
        selected_cfg, selected_signals, _, _, _, _ = candidate_trades[selected_key]
        selected_config = selected_cfg
        for cost in COSTS:
            oos = simulate(d, selected_signals, selected_cfg, *bounds["oos"], cost)
            cost_rows.append({
                **selected_cfg, "split": "oos", "cost_bps": cost, **metrics(oos)
            })
            if cost == 12:
                oos.to_csv(out_dir / "selected_oos_trades.csv", index=False)
                oos_summary = metrics(oos)
                if not oos.empty:
                    oos.assign(month=oos.exit_time.dt.strftime("%Y-%m")).groupby("month").agg(
                        trades=("net_R", "size"), net_R=("net_R", "sum"),
                        avg_R=("net_R", "mean")
                    ).reset_index().to_csv(out_dir / "selected_oos_monthly.csv", index=False)
                    oos.groupby("regime").net_R.agg(["count", "sum", "mean"]).reset_index().to_csv(
                        out_dir / "selected_oos_regimes.csv", index=False
                    )
    else:
        (out_dir / "oos_not_evaluated.txt").write_text(
            "No configuration passed both preregistered training and validation gates; OOS not evaluated.\n"
        )
    pd.DataFrame(cost_rows).to_csv(out_dir / "cost_sensitivity.csv", index=False)

    top_train = md.sort_values("train_net_R", ascending=False).head(10)
    top_val = md.sort_values("validation_net_R", ascending=False).head(10)
    top_train.to_csv(out_dir / "top_train.csv", index=False)
    top_val.to_csv(out_dir / "top_validation.csv", index=False)

    train_end = d.index[a]
    validation_end = d.index[b]
    meta = {
        "classification": "experimental research only; no live use",
        "symbol": "BTCUSD",
        "timeframe": "5m traded-price OHLCV; 15m/1h/4h derived only from complete 5m bars",
        "data": quality,
        "csv_sha256": sha256(price_path),
        "chronological_split": "70/15/15 by 5m row count",
        "train_end_utc": train_end.isoformat(),
        "validation_end_utc": validation_end.isoformat(),
        "configurations": len(configs),
        "training_eligible": int(len(eligible)),
        "training_shortlist": int(min(len(eligible), MAX_SHORTLIST)),
        "validation_passes": int(len(validation_pass_ids)),
        "oos_evaluated": oos_evaluated,
        "selected_config": selected_config,
        "selected_oos_12bp": oos_summary,
        "rules": {
            "trend": "completed 1h close > EMA50 > EMA200 for long; inverse for short",
            "vwap": "UTC-day anchored cumulative typical-price VWAP on completed 15m bars; 4-bar slope must agree; 15m close must be on trend side",
            "trigger": "completed 5m candle intersects a 0.10/0.20 ATR band around latest completed 15m VWAP; reclaim-close or close beyond prior 5m extreme; next 5m open entry",
            "volume": "none or current completed 5m volume >= 1.0/1.5 times median of prior 20 completed 5m bars",
            "stops_targets": "signal candle extreme or 1.0/1.5 x signal-bar ATR; target 1.5R/2R/3R; max hold 4h",
            "4h_filter": "optional completed 4h EMA50 slope over three completed 4h bars",
            "sessions": "all UTC hours, 07:00-13:00 UTC, 13:00-19:00 UTC",
        },
        "costs": "6/12/20bp assumed round trip on one BTC leg; primary matrix 12bp; exact fee tier, spread and market impact unverified; funding excluded",
        "fills": "next 5m open; same-bar stop first; adverse stop gap at worse open; target at target; no entry if next open is through stop",
        "selection": "train >=40 trades, PF>=1.05, positive net R, DD>=-20R, positive months>=50%; shortlist 25; validation >=20, PF>=1.05, positive net R, DD>=-12R, positive months>=50%; OOS once only after both gates",
        "lookahead_controls": "5m triggers use completed bars; higher-timeframe context is as-of joined at each higher-timeframe close; rolling volume median shifted one bar; all indicators reset at data gaps; incomplete aggregated bars excluded",
        "limitations": [
            "Delta candle volume is exchange-specific, not consolidated market volume.",
            "No account-specific fees, separate bid/ask spread, market impact or funding attribution.",
            "This is a single-instrument historical simulation; results require independent execution validation.",
        ],
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    print("\nTOP TRAINING\n", top_train[[
        "band_atr", "confirmation", "volume_mult", "stop", "target_r", "session",
        "four_hour_slope_filter", "train_trades", "train_win_rate_pct",
        "train_profit_factor", "train_net_R", "train_max_drawdown_R",
        "train_max_losing_streak", "train_positive_month_fraction",
    ]].to_string(index=False))
    print("\nTOP VALIDATION\n", top_val[[
        "band_atr", "confirmation", "volume_mult", "stop", "target_r", "session",
        "four_hour_slope_filter", "validation_trades", "validation_win_rate_pct",
        "validation_profit_factor", "validation_net_R", "validation_max_drawdown_R",
        "validation_max_losing_streak", "validation_positive_month_fraction",
    ]].to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)}; VALIDATION PASSES={len(validation_pass_ids)}; OOS={oos_evaluated}")


def self_test():
    # Same-bar stop and target: stop must win; adverse stop gap uses worse open.
    assert exit_fill(1, 100, 115, 85, 90, 110) == (90, "SL")
    assert exit_fill(-1, 100, 115, 85, 110, 90) == (110, "SL")
    assert exit_fill(1, 85, 95, 80, 90, 110) == (85, "SL")
    assert exit_fill(-1, 115, 120, 112, 110, 90) == (115, "SL")
    assert exit_fill(1, 100, 112, 95, 90, 110) == (110, "TP")

    # Context completed at 00:15 is unavailable to 00:00/00:05/00:10 bars.
    base = pd.DataFrame(
        {"segment": [1, 1, 1, 1]},
        index=pd.date_range("2026-01-01 00:00", periods=4, freq="5min", tz="UTC"),
    )
    base.index.name = "timestamp"
    ctx = pd.DataFrame(
        {"segment": [1], "marker": [123.0]},
        index=pd.DatetimeIndex(["2026-01-01 00:15"], tz="UTC", name="available_time"),
    )
    joined = attach_context(base, ctx)
    assert joined.marker.iloc[:3].isna().all()
    assert joined.marker.iloc[3] == 123.0

    # Volume baseline is shifted: a spike cannot raise its own threshold.
    vol = pd.Series([10.0] * 20 + [1000.0])
    med = vol.rolling(20, min_periods=20).median().shift(1)
    assert med.iloc[20] == 10.0

    # Signal construction requires trend, completed VWAP context and pullback.
    n = 3
    test = pd.DataFrame({
        "open": [100.0, 99.5, 100.0], "high": [100.5, 102.0, 101.0],
        "low": [99.0, 99.4, 99.5], "close": [99.0, 101.0, 100.5],
        "volume": [10.0, 20.0, 20.0], "atr5": [1.0] * n,
        "vol_median20": [10.0] * n, "vwap15": [100.0] * n,
        "vwap_slope4": [1.0] * n, "close15": [102.0] * n,
        "close1h": [110.0] * n, "ema50_1h": [105.0] * n,
        "ema200_1h": [100.0] * n, "ema50_slope3_4h": [1.0] * n,
        "segment": [1] * n, "vwap_day": [pd.Timestamp("2026-01-01", tz="UTC")] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"))
    sig = build_signals(test, 0.10, "reclaim_close", 1.0, False)
    assert any(x["signal_i"] == 1 and x["side"] == 1 for x in sig)
    print("8 deterministic VWAP trend-continuation tests passed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--price-5m-csv", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("results/btc-vwap-trend"))
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.price_5m_csv is None:
        p.error("--price-5m-csv is required unless --self-test is used")
    run(args.price_5m_csv, args.output_dir)


if __name__ == "__main__":
    main()
