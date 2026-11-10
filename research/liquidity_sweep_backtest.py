"""BTCUSD 15m liquidity-sweep reversal research with confirmed 1H pivots.

A 1H pivot becomes usable only after three subsequent complete 1H bars close.
A 15m wick through the latest active pivot followed by a close back inside is a
sweep. Entry is next 15m open, or after a break of the sweep candle in the
reversal direction. Each pivot level is consumed once. Experimental only.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("liquidity_sweep_results")
OUT.mkdir(exist_ok=True)
COST_RATE = 0.0012
ATR_LEN = 14
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
SWEEP_ATR = (0.0, 0.1)
CONFIRMS = ("reclaim", "break_sweep")
STOP_BUFFERS = (0.0, 0.1)
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_aligned")
SESSIONS = ("all", "london_ny_utc")
MAX_HOLD = pd.Timedelta("48h")
BAR = pd.Timedelta("15min")


def rma(series, length):
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < length or not np.isfinite(values[:length]).all():
        return pd.Series(out, index=series.index)
    out[length - 1] = float(np.mean(values[:length]))
    for i in range(length, len(values)):
        if np.isfinite(values[i]):
            out[i] = (out[i - 1] * (length - 1) + values[i]) / length
    return pd.Series(out, index=series.index)


def prepare_data(raw):
    d = raw.sort_index().copy()
    previous = d.close.shift()
    true_range = pd.concat(
        [d.high - d.low, (d.high - previous).abs(), (d.low - previous).abs()],
        axis=1,
    ).max(axis=1)
    d["atr15"] = rma(true_range, ATR_LEN)

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    # Right-labelled 1H bars expose EMA only after the hour has completed.
    d["ema50_1h"] = hourly["ema50"].reindex(d.index, method="ffill")
    return d, hourly


def pivot_events(d, hourly):
    high_events, low_events = {}, {}
    hi = hourly.high.to_numpy(float)
    lo = hourly.low.to_numpy(float)
    times = hourly.index
    for i in range(PIVOT_LEFT, len(hourly) - PIVOT_RIGHT):
        window_times = times[i - PIVOT_LEFT : i + PIVOT_RIGHT + 1]
        if (window_times.to_series().diff().dropna() != pd.Timedelta("1h")).any():
            continue
        pivot_time = times[i]
        confirm_time = times[i + PIVOT_RIGHT]
        pos = d.index.searchsorted(confirm_time, side="left")
        if pos >= len(d):
            continue
        if hi[i] > np.max(hi[i - PIVOT_LEFT : i]) and hi[i] > np.max(
            hi[i + 1 : i + PIVOT_RIGHT + 1]
        ):
            high_events.setdefault(pos, []).append((float(hi[i]), pivot_time))
        if lo[i] < np.min(lo[i - PIVOT_LEFT : i]) and lo[i] < np.min(
            lo[i + 1 : i + PIVOT_RIGHT + 1]
        ):
            low_events.setdefault(pos, []).append((float(lo[i]), pivot_time))
    return high_events, low_events


def build_signals(d, high_events, low_events, sweep_atr, confirm_mode):
    """Build causal one-shot sweep signals for one sweep threshold/confirmation."""
    o = d.open.to_numpy(float)
    h = d.high.to_numpy(float)
    l = d.low.to_numpy(float)
    c = d.close.to_numpy(float)
    atr = d.atr15.to_numpy(float)
    active_high = None
    active_low = None
    signals = []

    for i in range(len(d)):
        if i in high_events:
            active_high = high_events[i][-1]
        if i in low_events:
            active_low = low_events[i][-1]
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        hit_high = (
            active_high is not None
            and h[i] > active_high[0] + sweep_atr * atr[i]
            and c[i] < active_high[0]
        )
        hit_low = (
            active_low is not None
            and l[i] < active_low[0] - sweep_atr * atr[i]
            and c[i] > active_low[0]
        )
        invalidate_high = (
            active_high is not None
            and h[i] > active_high[0]
            and c[i] >= active_high[0]
        )
        invalidate_low = (
            active_low is not None
            and l[i] < active_low[0]
            and c[i] <= active_low[0]
        )

        if hit_high and hit_low:
            active_high = None
            active_low = None
            continue
        if invalidate_high:
            active_high = None
        if invalidate_low:
            active_low = None
        if not (hit_high or hit_low):
            continue

        if hit_low:
            level, level_time = active_low
            side, extreme = "long", float(l[i])
            active_low = None
        else:
            level, level_time = active_high
            side, extreme = "short", float(h[i])
            active_high = None

        confirm_i = i
        if confirm_mode == "break_sweep":
            found = None
            for j in range(i + 1, min(i + 5, len(d) - 1)):
                # Reject confirmation if the sweep extreme is retaken before entry.
                stopped_before_entry = (
                    l[j] <= extreme if side == "long" else h[j] >= extreme
                )
                if stopped_before_entry:
                    break
                broke = c[j] > h[i] if side == "long" else c[j] < l[i]
                if broke:
                    found = j
                    break
            if found is None:
                continue
            confirm_i = found

        entry_i = confirm_i + 1
        if entry_i >= len(d):
            continue
        signals.append(
            {
                "signal_i": i,
                "confirm_i": confirm_i,
                "entry_i": entry_i,
                "side": side,
                "level": float(level),
                "level_time": level_time,
                "extreme": extreme,
                "atr_sweep": float(atr[i]),
            }
        )
    return sorted(signals, key=lambda item: item["entry_i"])


def metrics(group):
    g = group.sort_values("entry_time")
    r = g.net_R.astype(float)
    positive, negative = r[r > 0], r[r < 0]
    equity = r.cumsum().to_numpy()
    drawdown = equity - np.maximum.accumulate(np.r_[0.0, equity])[1:]
    streak = max_streak = 0
    for value in r:
        streak = streak + 1 if value < 0 else 0
        max_streak = max(max_streak, streak)
    return {
        "trades": int(len(g)),
        "profitable_pct": round(float((r > 0).mean() * 100), 2),
        "tp_rate_pct": round(float((g.outcome == "TP").mean() * 100), 2),
        "profit_factor": round(float(positive.sum() / abs(negative.sum())), 3)
        if len(negative) and negative.sum() != 0
        else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, drawdown.min())), 2),
        "max_losing_streak": int(max_streak),
        "TP": int((g.outcome == "TP").sum()),
        "SL": int((g.outcome == "SL").sum()),
        "TIME": int((g.outcome == "TIME").sum()),
    }


def run_config(d, signals, sample, split_i, sweep_atr, confirm_mode,
               stop_buffer, target_r, filter_mode, session_mode):
    n = len(d)
    start_i = 0 if sample == "train" else split_i
    end_i = split_i if sample == "train" else n
    segment_end = d.index[end_i] if end_i < n else d.index[-1] + BAR
    idx = d.index
    opens = d.open.to_numpy(float)
    highs = d.high.to_numpy(float)
    lows = d.low.to_numpy(float)
    closes = d.close.to_numpy(float)
    ema = d.ema50_1h.to_numpy(float)
    trades = []
    last_exit_time = None

    for signal in signals:
        entry_i = signal["entry_i"]
        entry_time = idx[entry_i]
        if entry_i < start_i or entry_i >= end_i:
            continue
        if entry_time + MAX_HOLD > segment_end:
            continue
        if session_mode == "london_ny_utc" and not (7 <= entry_time.hour < 22):
            continue

        confirm_i = signal["confirm_i"]
        side = signal["side"]
        if filter_mode == "ema50_aligned":
            e = ema[confirm_i]
            if not np.isfinite(e):
                continue
            if (side == "long" and closes[confirm_i] <= e) or (
                side == "short" and closes[confirm_i] >= e
            ):
                continue
        if last_exit_time is not None and entry_time < last_exit_time + BAR:
            continue

        entry = float(opens[entry_i])
        pad = stop_buffer * signal["atr_sweep"]
        stop = signal["extreme"] - pad if side == "long" else signal["extreme"] + pad
        risk = entry - stop if side == "long" else stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry + target_r * risk if side == "long" else entry - target_r * risk

        stop_i = idx.searchsorted(entry_time + MAX_HOLD, side="left")
        if stop_i <= entry_i:
            continue
        # Never bridge a missing 15m interval inside a simulated holding window.
        segment_times = idx[entry_i:stop_i]
        if len(segment_times) > 1 and (
            segment_times.to_series().diff().dropna() != BAR
        ).any():
            continue

        outcome = "TIME"
        exit_price = float(closes[stop_i - 1])
        exit_i = stop_i - 1
        for j in range(entry_i, stop_i):
            op, bh, bl = opens[j], highs[j], lows[j]
            stop_hit = bl <= stop if side == "long" else bh >= stop
            target_hit = bh >= target if side == "long" else bl <= target
            if stop_hit:
                outcome = "SL"
                exit_price = min(stop, op) if side == "long" else max(stop, op)
                exit_i = j
                break
            if target_hit:
                outcome = "TP"
                exit_price = target
                exit_i = j
                break

        gross_r = (
            (exit_price - entry) / risk
            if side == "long"
            else (entry - exit_price) / risk
        )
        cost_r = COST_RATE * entry / risk
        trades.append(
            {
                "sample": sample,
                "sweep_atr": sweep_atr,
                "confirm": confirm_mode,
                "stop_buffer_atr": stop_buffer,
                "target_R": target_r,
                "filter": filter_mode,
                "session": session_mode,
                "side": side,
                "level_time": signal["level_time"],
                "signal_time": idx[signal["signal_i"]],
                "confirm_time": idx[confirm_i],
                "entry_time": entry_time,
                "exit_time": idx[exit_i],
                "level": signal["level"],
                "sweep_extreme": signal["extreme"],
                "entry": entry,
                "stop": stop,
                "target": target,
                "exit": exit_price,
                "outcome": outcome,
                "gross_R": gross_r,
                "cost_R": cost_r,
                "net_R": gross_r - cost_r,
            }
        )
        last_exit_time = idx[exit_i]
    return trades


def main():
    raw = fetch("15m")
    d, hourly = prepare_data(raw)
    gaps = d.index.to_series().diff().dropna()
    gap_count = int((gaps != BAR).sum())
    split_i = int(len(d) * 0.70)
    split_time = d.index[split_i]
    high_events, low_events = pivot_events(d, hourly)

    signal_cache = {}
    for sweep_atr in SWEEP_ATR:
        for confirm_mode in CONFIRMS:
            signal_cache[(sweep_atr, confirm_mode)] = build_signals(
                d, high_events, low_events, sweep_atr, confirm_mode
            )

    all_trades = []
    for sweep_atr in SWEEP_ATR:
        for confirm_mode in CONFIRMS:
            signals = signal_cache[(sweep_atr, confirm_mode)]
            for stop_buffer in STOP_BUFFERS:
                for target_r in TARGETS_R:
                    for filter_mode in FILTERS:
                        for session_mode in SESSIONS:
                            for sample in ("train", "test"):
                                all_trades.extend(
                                    run_config(
                                        d, signals, sample, split_i, sweep_atr,
                                        confirm_mode, stop_buffer, target_r,
                                        filter_mode, session_mode,
                                    )
                                )
    if not all_trades:
        raise RuntimeError("No liquidity-sweep trades generated.")

    trades = pd.DataFrame(all_trades).sort_values("entry_time")
    trades.to_csv(OUT / "liquidity_sweep_trades.csv", index=False)
    keys = [
        "sweep_atr", "confirm", "stop_buffer_atr", "target_R",
        "filter", "session", "sample",
    ]
    summary_rows = []
    for key, group in trades.groupby(keys, sort=False):
        values = key if isinstance(key, tuple) else (key,)
        summary_rows.append(dict(zip(keys, values)) | metrics(group))
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "liquidity_sweep_summary.csv", index=False)

    monthly_rows = []
    monthly_trades = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"))
    for key, group in monthly_trades.groupby(keys + ["month"], sort=False):
        values = key if isinstance(key, tuple) else (key,)
        monthly_rows.append(dict(zip(keys + ["month"], values)) | metrics(group))
    monthly = pd.DataFrame(monthly_rows)
    monthly.to_csv(OUT / "liquidity_sweep_monthly.csv", index=False)

    data_path = Path("crt_results/BTCUSD_15m.csv")
    data_hash = hashlib.sha256(data_path.read_bytes()).hexdigest() if data_path.exists() else None
    meta = {
        "symbol": "BTCUSD",
        "rows_15m": len(d),
        "start": str(d.index.min()),
        "end": str(d.index.max()),
        "gaps_15m": gap_count,
        "sha256_15m_csv": data_hash,
        "rows_complete_1h": len(hourly),
        "confirmed_pivot_left_right": [PIVOT_LEFT, PIVOT_RIGHT],
        "oos_split": str(split_time),
        "configurations": 96,
        "sweep_atr": SWEEP_ATR,
        "confirmations": CONFIRMS,
        "stop_buffers_atr15m": STOP_BUFFERS,
        "targets_R": TARGETS_R,
        "filters": FILTERS,
        "sessions": SESSIONS,
        "max_holding": str(MAX_HOLD),
        "round_trip_cost_assumption": COST_RATE,
        "notes": [
            "1H pivots use strict 3-left/3-right highs/lows and become available only after the third right-hand hour closes",
            "Only the latest confirmed pivot high and low are active; each is consumed once by a sweep or breakout invalidation",
            "Sweep requires a wick beyond the pivot and a 15m close back inside; simultaneous high/low sweeps are skipped",
            "break_sweep waits up to four 15m bars for a close beyond the sweep candle in the reversal direction and rejects a retaken sweep extreme",
            "EMA50 filter uses completed right-labelled 1H bars; London/New York proxy is fixed UTC 07:00-22:00 and does not model DST",
            "Entry at next 15m open; one position at a time per exact configuration; 48h maximum hold",
            "Stop at sweep extreme plus optional 15m ATR buffer; fixed 1.5R/2R/3R target",
            "Same-bar SL/TP resolved SL first; adverse gap-through stop fill; stop distances above 5% of entry skipped",
            "12bp assumed round-trip costs; no funding or separate spread/slippage model",
            "Chronological 70/30 split; signals and pivots are causal; trades crossing sample boundaries are skipped",
            "Exploratory matrix only; no production changes or live signals",
        ],
    }
    (OUT / "liquidity_sweep_methodology.json").write_text(json.dumps(meta, indent=2))
    print("LIQUIDITY SWEEP META", json.dumps(meta))
    print("OOS SUMMARY")
    print(
        summary[summary["sample"] == "test"]
        .sort_values("net_R", ascending=False)
        .head(30)
        .to_string(index=False)
    )
    print("OOS MONTHLY")
    print(
        monthly[monthly["sample"] == "test"]
        .sort_values(["sweep_atr", "confirm", "stop_buffer_atr", "target_R", "filter", "session", "month"])
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
