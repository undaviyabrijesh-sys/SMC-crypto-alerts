"""Intraday BTCUSD support/resistance rejection research.

Levels: prior completed UTC-day high/low and causally confirmed 4H swing pivots.
Execution: 15m rejection/reclaim, optional break of rejection candle, next-open entry.
Maximum holding period: 8 hours. Train/validation selection only; OOS once.
Research only; no production or live-trading changes.
"""
import bisect
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("sr_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
MAX_CONFIRM_BARS = 4
COST_RATE = 0.0012  # assumed 12bp round trip; actual fee tier not verified
LEVEL_FAMILIES = ("previous_day", "h4_2_2", "h4_3_3")
PENETRATIONS = (0.0, 0.1)
CONFIRMATIONS = ("reclaim", "break_rejection")
STOPS = ("structure_0p1atr", "atr1", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h")
SESSIONS = ("all", "00-07", "07-13", "13-19", "19-24")
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MAX_TRAIN_CANDIDATES = 25


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
    d = d[~d.index.duplicated(keep="last")]
    previous = d.close.shift(1)
    tr = pd.concat(
        [d.high - d.low, (d.high - previous).abs(), (d.low - previous).abs()],
        axis=1,
    ).max(axis=1)
    d["atr15"] = rma(tr, 14)

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    h_count = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[h_count.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(span=50, adjust=False, min_periods=50).mean()
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")

    daily = d.resample("1D", label="right", closed="left").agg(
        {"high": "max", "low": "min"}
    )
    day_count = d.close.resample("1D", label="right", closed="left").count()
    daily = daily.loc[day_count.reindex(daily.index).eq(96)]
    # For a 15m bar on date D, the daily bar labelled D 00:00 is the
    # fully completed UTC day D-1. No current-day high/low is referenced.
    day_labels = d.index.normalize()
    d["prev_day_high"] = daily.high.reindex(day_labels).to_numpy()
    d["prev_day_low"] = daily.low.reindex(day_labels).to_numpy()

    h4 = d.resample("4h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    h4_count = d.close.resample("4h", label="right", closed="left").count()
    h4 = h4.loc[h4_count.reindex(h4.index).eq(16)].dropna()
    return d, hourly, h4, daily


def pivot_events(d, h4, strength):
    high_events, low_events = {}, {}
    highs = h4.high.to_numpy(dtype=float)
    lows = h4.low.to_numpy(dtype=float)
    times = h4.index
    for i in range(strength, len(h4) - strength):
        window = times[i - strength : i + strength + 1]
        if len(window) != 2 * strength + 1:
            continue
        if (window.to_series().diff().dropna() != pd.Timedelta("4h")).any():
            continue
        is_high = highs[i] > np.max(highs[i-strength:i]) and highs[i] > np.max(highs[i+1:i+strength+1])
        is_low = lows[i] < np.min(lows[i-strength:i]) and lows[i] < np.min(lows[i+1:i+strength+1])
        available_at = times[i + strength]
        pos = int(d.index.searchsorted(available_at, side="left"))
        if pos >= len(d):
            continue
        if is_high:
            high_events.setdefault(pos, []).append((float(highs[i]), available_at))
        if is_low:
            low_events.setdefault(pos, []).append((float(lows[i]), available_at))
    return high_events, low_events


def confirmation_index(i, side, level, mode, limit, highs, lows, closes):
    if mode == "reclaim":
        return i
    stop = min(limit, i + MAX_CONFIRM_BARS)
    for j in range(i + 1, stop + 1):
        if side == "short":
            if closes[j] >= level:
                return None
            if closes[j] < lows[i]:
                return j
        else:
            if closes[j] <= level:
                return None
            if closes[j] > highs[i]:
                return j
    return None


def build_signals(d, family, penetration, confirmation, h4):
    high = d.high.to_numpy(dtype=float)
    low = d.low.to_numpy(dtype=float)
    close = d.close.to_numpy(dtype=float)
    atr = d.atr15.to_numpy(dtype=float)
    idx = d.index
    n = len(d)
    signals = []

    if family == "previous_day":
        level_high = d.prev_day_high.to_numpy(dtype=float)
        level_low = d.prev_day_low.to_numpy(dtype=float)
        day_ns = idx.normalize().asi8
        day_starts = np.r_[0, np.flatnonzero(np.diff(day_ns)) + 1]
        day_ends = np.r_[day_starts[1:] - 1, n - 1]
        day_end_for_i = np.empty(n, dtype=int)
        for a, b in zip(day_starts, day_ends):
            day_end_for_i[a:b+1] = b
        used_high = used_low = False
        current_day = None
        for i in range(1, n - 1):
            if day_ns[i] != current_day:
                current_day = day_ns[i]
                used_high = used_low = False
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            if not used_high and np.isfinite(level_high[i]):
                level = level_high[i]
                if high[i] >= level + penetration * atr[i] and close[i] < level:
                    used_high = True
                    sig_i = confirmation_index(i, "short", level, confirmation, day_end_for_i[i], high, low, close)
                    if sig_i is not None and sig_i < n - 1:
                        signals.append({"setup_i": i, "signal_i": sig_i, "entry_i": sig_i + 1,
                                        "side": "short", "level": level, "extreme": high[i],
                                        "atr_setup": atr[i], "atr_signal": atr[sig_i], "family": family})
            if not used_low and np.isfinite(level_low[i]):
                level = level_low[i]
                if low[i] <= level - penetration * atr[i] and close[i] > level:
                    used_low = True
                    sig_i = confirmation_index(i, "long", level, confirmation, day_end_for_i[i], high, low, close)
                    if sig_i is not None and sig_i < n - 1:
                        signals.append({"setup_i": i, "signal_i": sig_i, "entry_i": sig_i + 1,
                                        "side": "long", "level": level, "extreme": low[i],
                                        "atr_setup": atr[i], "atr_signal": atr[sig_i], "family": family})
        return sorted(signals, key=lambda x: x["entry_i"])

    strength = 2 if family == "h4_2_2" else 3
    high_events, low_events = pivot_events(d, h4, strength)
    high_positions = sorted(high_events)
    low_positions = sorted(low_events)
    active_high = None
    active_low = None
    for i in range(1, n - 1):
        if i in high_events:
            active_high = {"level": high_events[i][-1][0], "used": False}
        if i in low_events:
            active_low = {"level": low_events[i][-1][0], "used": False}
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        if active_high is not None:
            level = active_high["level"]
            if close[i] > level:
                active_high = None
            elif not active_high["used"] and high[i] >= level + penetration * atr[i] and close[i] < level:
                active_high["used"] = True
                k = bisect.bisect_right(high_positions, i)
                next_pivot = high_positions[k] if k < len(high_positions) else n - 1
                limit = min(i + MAX_CONFIRM_BARS, next_pivot - 1)
                sig_i = confirmation_index(i, "short", level, confirmation, limit, high, low, close)
                if sig_i is not None and sig_i < n - 1:
                    signals.append({"setup_i": i, "signal_i": sig_i, "entry_i": sig_i + 1,
                                    "side": "short", "level": level, "extreme": high[i],
                                    "atr_setup": atr[i], "atr_signal": atr[sig_i], "family": family})

        if active_low is not None:
            level = active_low["level"]
            if close[i] < level:
                active_low = None
            elif not active_low["used"] and low[i] <= level - penetration * atr[i] and close[i] > level:
                active_low["used"] = True
                k = bisect.bisect_right(low_positions, i)
                next_pivot = low_positions[k] if k < len(low_positions) else n - 1
                limit = min(i + MAX_CONFIRM_BARS, next_pivot - 1)
                sig_i = confirmation_index(i, "long", level, confirmation, limit, high, low, close)
                if sig_i is not None and sig_i < n - 1:
                    signals.append({"setup_i": i, "signal_i": sig_i, "entry_i": sig_i + 1,
                                    "side": "long", "level": level, "extreme": low[i],
                                    "atr_setup": atr[i], "atr_signal": atr[sig_i], "family": family})
    return sorted(signals, key=lambda x: x["entry_i"])


def in_session(ts, session):
    if session == "all":
        return True
    bounds = {"00-07": (0, 7), "07-13": (7, 13), "13-19": (13, 19), "19-24": (19, 24)}
    lo, hi = bounds[session]
    return lo <= ts.hour < hi


def max_losing_streak(values):
    current = maximum = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum


def metrics(trades):
    if trades.empty:
        return {"trades": 0, "profitable_pct": 0.0, "profit_factor": None, "net_R": 0.0,
                "avg_R": 0.0, "max_drawdown_R": 0.0, "max_losing_streak": 0,
                "TP": 0, "SL": 0, "TIME": 0, "positive_month_fraction": 0.0}
    g = trades.sort_values("entry_time")
    r = g.net_R.astype(float)
    wins, losses = r[r > 0], r[r < 0]
    equity = r.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    dd = equity - peak
    monthly = g.assign(month=g.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(g)),
        "profitable_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) and abs(losses.sum()) else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 2),
        "max_losing_streak": int(max_losing_streak(r.to_numpy())),
        "TP": int((g.outcome == "TP").sum()),
        "SL": int((g.outcome == "SL").sum()),
        "TIME": int((g.outcome == "TIME").sum()),
        "long_trades": int((g.side == "long").sum()),
        "short_trades": int((g.side == "short").sum()),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3) if len(monthly) else 0.0,
    }


def simulate(d, signals, config, start_i, end_i, gap_mask):
    opens = d.open.to_numpy(dtype=float)
    highs = d.high.to_numpy(dtype=float)
    lows = d.low.to_numpy(dtype=float)
    closes = d.close.to_numpy(dtype=float)
    ema = d.ema50_1h.to_numpy(dtype=float)
    idx = d.index
    rows = []
    last_exit = -1
    for sig in signals:
        entry_i, signal_i, setup_i = sig["entry_i"], sig["signal_i"], sig["setup_i"]
        if entry_i < start_i or entry_i >= end_i or entry_i <= last_exit:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if not in_session(idx[entry_i], config["session"]):
            continue
        side = sig["side"]
        if config["filter"] == "ema50_1h":
            e = ema[signal_i]
            if not np.isfinite(e) or (side == "long" and closes[signal_i] <= e) or (side == "short" and closes[signal_i] >= e):
                continue
        if gap_mask[setup_i : entry_i + MAX_HOLD_BARS].any():
            continue
        entry = float(opens[entry_i])
        if config["stop"] == "structure_0p1atr":
            pad = 0.1 * sig["atr_setup"]
            stop = sig["extreme"] - pad if side == "long" else sig["extreme"] + pad
        else:
            mult = 1.0 if config["stop"] == "atr1" else 1.5
            dist = mult * sig["atr_signal"]
            stop = entry - dist if side == "long" else entry + dist
        risk = entry - stop if side == "long" else stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry + config["target_r"] * risk if side == "long" else entry - config["target_r"] * risk

        outcome = "TIME"
        exit_i = entry_i + MAX_HOLD_BARS - 1
        exit_price = float(closes[exit_i])
        for j in range(entry_i, entry_i + MAX_HOLD_BARS):
            stop_hit = lows[j] <= stop if side == "long" else highs[j] >= stop
            target_hit = highs[j] >= target if side == "long" else lows[j] <= target
            if stop_hit:
                outcome = "SL"
                exit_price = min(stop, float(opens[j])) if side == "long" else max(stop, float(opens[j]))
                exit_i = j
                break
            if target_hit:
                outcome = "TP"
                exit_price = target
                exit_i = j
                break
        gross_r = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        cost_r = entry * COST_RATE / risk
        rows.append({
            "entry_time": idx[entry_i], "exit_time": idx[exit_i], "side": side,
            "level_family": sig["family"], "level": sig["level"], "entry": entry,
            "stop": stop, "target": target, "exit": exit_price, "outcome": outcome,
            "gross_R": gross_r, "estimated_cost_R": cost_r, "net_R": gross_r - cost_r,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def main():
    raw = fetch("15m")
    d, hourly, h4, daily = prepare_data(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m history: {len(d)} rows")
    n = len(d)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    segments = {"train": (0, train_end), "validation": (train_end, validation_end), "oos": (validation_end, n)}
    diffs = d.index.to_series().diff()
    gap_mask = diffs.ne(BAR).to_numpy(copy=True)
    gap_mask[0] = False

    data_path = OUT / "BTCUSD_15m.csv"
    d.to_csv(data_path)
    data_quality = {
        "symbol": "BTCUSD", "timeframe": "15m", "rows": int(n),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps": int((diffs.dropna() != BAR).sum()),
        "largest_gap_minutes": float(diffs.dropna().max().total_seconds() / 60),
        "hourly_complete_bars": int(len(hourly)), "four_hour_complete_bars": int(len(h4)),
        "complete_daily_bars": int(len(daily)),
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    configs = []
    for family, penetration, confirmation in itertools.product(LEVEL_FAMILIES, PENETRATIONS, CONFIRMATIONS):
        key = (family, penetration, confirmation)
        signal_cache[key] = build_signals(d, family, penetration, confirmation, h4)
    for family, penetration, confirmation, stop, target, filt, session in itertools.product(
        LEVEL_FAMILIES, PENETRATIONS, CONFIRMATIONS, STOPS, TARGETS_R, FILTERS, SESSIONS
    ):
        key = (family, penetration, confirmation)
        cid = f"{family}_pen{str(penetration).replace('.', 'p')}_{confirmation}_{stop}_{str(target).replace('.', 'p')}R_{filt}_{session}"
        configs.append({"config_id": cid, "family": family, "penetration_atr": penetration,
                        "confirmation": confirmation, "stop": stop, "target_r": target,
                        "filter": filt, "session": session, "signals": signal_cache[key]})

    train_rows, validation_rows = [], []
    for c in configs:
        base = {k: v for k, v in c.items() if k != "signals"}
        for sample in ("train", "validation"):
            t = simulate(d, c["signals"], c, *segments[sample], gap_mask)
            row = base | {"sample": sample} | metrics(t)
            (train_rows if sample == "train" else validation_rows).append(row)

    train_df = pd.DataFrame(train_rows)
    validation_df = pd.DataFrame(validation_rows)
    train_df.to_csv(OUT / "train_summary.csv", index=False)
    validation_df.to_csv(OUT / "validation_summary.csv", index=False)

    eligible_train = train_df[
        (train_df.trades >= MIN_TRAIN_TRADES) & (train_df.net_R > 0)
        & (train_df.profit_factor >= 1.05) & (train_df.max_drawdown_R >= -25.0)
    ].copy()
    if not eligible_train.empty:
        eligible_train["train_quality"] = eligible_train.net_R / eligible_train.max_drawdown_R.abs().clip(lower=1.0)
        shortlist = eligible_train.sort_values(["train_quality", "trades"], ascending=[False, False]).head(MAX_TRAIN_CANDIDATES)
        eligible_validation = validation_df[
            validation_df.config_id.isin(shortlist.config_id)
            & (validation_df.trades >= MIN_VALIDATION_TRADES)
            & (validation_df.net_R > 0) & (validation_df.profit_factor >= 1.05)
            & (validation_df.max_drawdown_R >= -15.0)
            & (validation_df.positive_month_fraction >= 0.50)
        ].copy()
    else:
        shortlist = pd.DataFrame()
        eligible_validation = pd.DataFrame()

    oos_summary = {}
    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = eligible_validation.net_R / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        selected = eligible_validation.sort_values(["validation_quality", "trades"], ascending=[False, False]).iloc[0]
        config = next(c for c in configs if c["config_id"] == selected.config_id)
        oos = simulate(d, config["signals"], config, *segments["oos"], gap_mask)
        oos.to_csv(OUT / "oos_trades.csv", index=False)
        oos_summary = metrics(oos)
        pd.DataFrame([oos_summary | {"config_id": selected.config_id}]).to_csv(OUT / "selected_oos_summary.csv", index=False)
        if not oos.empty:
            monthly = oos.assign(month=oos.entry_time.dt.strftime("%Y-%m")).groupby("month").agg(
                trades=("net_R", "size"), net_R=("net_R", "sum"),
                profitable_pct=("net_R", lambda x: float((x > 0).mean() * 100))
            ).reset_index()
            monthly.to_csv(OUT / "oos_monthly.csv", index=False)
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation funnel; OOS was not evaluated."
        )

    top_train = train_df.sort_values("net_R", ascending=False).head(5)
    top_validation = validation_df.sort_values("net_R", ascending=False).head(5)
    top_train.to_csv(OUT / "top_train.csv", index=False)
    top_validation.to_csv(OUT / "top_validation.csv", index=False)
    meta = {
        "matrix_configurations": len(configs), "train_eligible": int(len(eligible_train)),
        "train_shortlist": int(len(shortlist)), "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(not eligible_validation.empty), "oos_summary": oos_summary,
        "cost_assumption": "12bp round trip; actual fee tier not verified; no funding or separate spread/slippage model",
        "execution": "15m next-open entries; 8h max hold; SL first; adverse gap-through stop fills; one position/configuration",
        "split": "chronological 70/15/15; OOS only for the single validation-selected configuration",
        "level_causality": "previous completed UTC-day levels; strict 4H pivots become available after right-side confirmation bars close",
    }
    (OUT / "methodology.json").write_text(json.dumps(meta, indent=2))
    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"CONFIGURATIONS: {len(configs)}")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(shortlist)}; VALIDATION PASS: {len(eligible_validation)}")
    print("TOP TRAIN")
    print(top_train[["config_id", "trades", "profitable_pct", "profit_factor", "net_R", "max_drawdown_R", "max_losing_streak"]].to_string(index=False))
    print("TOP VALIDATION")
    print(top_validation[["config_id", "trades", "profitable_pct", "profit_factor", "net_R", "max_drawdown_R", "max_losing_streak"]].to_string(index=False))
    if eligible_validation.empty:
        print("NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; OOS WAS NOT EVALUATED.")
    else:
        print("SELECTED OOS SUMMARY")
        print(json.dumps(oos_summary, indent=2))
    print(f"Artifacts written to {OUT}/")


if __name__ == "__main__":
    main()
