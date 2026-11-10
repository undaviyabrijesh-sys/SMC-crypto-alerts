"""Intraday BTCUSD Supertrend flip continuation research.

Supertrend is calculated causally from completed 15m OHLC bars using Wilder
RMA ATR and TradingView-style final-band recurrence. A confirmed flip enters
at the next 15m open; the signal-bar Supertrend line is the fixed stop.
Every trade is capped at 8h. OOS is only evaluated after train/validation pass.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("supertrend_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_RATE = 0.0012
SOURCES = ("hl2", "ema50_15m")
ATR_LENGTHS = (7, 10)
ATR_MULTIPLIERS = (2.0, 2.5, 3.0)
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "00-07", "07-13", "13-19", "19-24")
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MAX_TRAIN_CANDIDATES = 25


def rma(series, length):
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    valid = np.flatnonzero(np.isfinite(values))
    if len(valid) < length:
        return pd.Series(out, index=series.index)
    first = int(valid[0])
    seed_end = first + length
    if seed_end > len(values) or not np.isfinite(values[first:seed_end]).all():
        return pd.Series(out, index=series.index)
    out[seed_end - 1] = float(np.mean(values[first:seed_end]))
    for i in range(seed_end, len(values)):
        if np.isfinite(values[i]):
            out[i] = (out[i - 1] * (length - 1) + values[i]) / length
    return pd.Series(out, index=series.index)


def prepare_base(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    prev = d.close.shift(1)
    tr = pd.concat(
        [d.high - d.low, (d.high - prev).abs(), (d.low - prev).abs()],
        axis=1,
    ).max(axis=1)
    d["ema50_15m"] = d.close.ewm(span=50, adjust=False, min_periods=1).mean()

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    # Hourly values become visible only at their right-edge close timestamp.
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    return d, tr, hourly


def build_supertrend(d, tr, source, atr_len, multiplier):
    atr = rma(tr, atr_len)
    src = (
        (d.high + d.low) / 2.0
        if source == "hl2"
        else d.ema50_15m
    )
    basic_upper = (src + multiplier * atr).to_numpy(dtype=float)
    basic_lower = (src - multiplier * atr).to_numpy(dtype=float)
    close = d.close.to_numpy(dtype=float)
    n = len(d)
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    direction = np.ones(n, dtype=np.int8)
    st_line = np.full(n, np.nan)

    for i in range(n):
        if not np.isfinite(atr.iloc[i]):
            continue
        if i == 0 or not np.isfinite(final_upper[i - 1]):
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            direction[i] = 1  # initial state is downtrend / upper band
            st_line[i] = final_upper[i]
            continue
        final_lower[i] = (
            basic_lower[i]
            if (basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1])
            else final_lower[i - 1]
        )
        final_upper[i] = (
            basic_upper[i]
            if (basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1])
            else final_upper[i - 1]
        )
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] > final_upper[i] else 1
        else:
            direction[i] = 1 if close[i] < final_lower[i] else -1
        st_line[i] = final_lower[i] if direction[i] == -1 else final_upper[i]

    return atr, direction, st_line


def build_signals(d, tr, source, atr_len, multiplier):
    atr, direction, st_line = build_supertrend(d, tr, source, atr_len, multiplier)
    signals = []
    close = d.close.to_numpy(dtype=float)
    idx = d.index
    for i in range(1, len(d) - 1):
        if not np.isfinite(st_line[i]) or not np.isfinite(st_line[i - 1]):
            continue
        long_flip = direction[i - 1] == 1 and direction[i] == -1
        short_flip = direction[i - 1] == -1 and direction[i] == 1
        if not (long_flip or short_flip):
            continue
        side = "long" if long_flip else "short"
        signals.append({
            "signal_i": i,
            "entry_i": i + 1,
            "side": side,
            "stop_line": float(st_line[i]),
            "signal_close": float(close[i]),
            "atr_signal": float(atr.iloc[i]),
        })
    return signals


def in_session(ts, session):
    if session == "all":
        return True
    bounds = {
        "00-07": (0, 7), "07-13": (7, 13),
        "13-19": (13, 19), "19-24": (19, 24),
    }
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
        return {
            "trades": 0, "profitable_pct": 0.0, "profit_factor": None,
            "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "TP": 0, "SL": 0, "TIME": 0,
            "positive_month_fraction": 0.0, "long_trades": 0, "short_trades": 0,
        }
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
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 2),
        "max_losing_streak": int(max_losing_streak(r.to_numpy())),
        "TP": int((g.outcome == "TP").sum()),
        "SL": int((g.outcome == "SL").sum()),
        "TIME": int((g.outcome == "TIME").sum()),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3) if len(monthly) else 0.0,
        "long_trades": int((g.side == "long").sum()),
        "short_trades": int((g.side == "short").sum()),
    }


def simulate(d, signals, config, start_i, end_i, gap_mask):
    opens = d.open.to_numpy(dtype=float)
    highs = d.high.to_numpy(dtype=float)
    lows = d.low.to_numpy(dtype=float)
    closes = d.close.to_numpy(dtype=float)
    ema1h = d.ema50_1h.to_numpy(dtype=float)
    idx = d.index
    rows = []
    last_exit = -1

    for sig in signals:
        signal_i, entry_i = sig["signal_i"], sig["entry_i"]
        if entry_i < start_i or entry_i >= end_i or entry_i <= last_exit:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if gap_mask[signal_i:entry_i + MAX_HOLD_BARS].any():
            continue

        side = sig["side"]
        if config["direction"] == "long_only" and side != "long":
            continue
        if config["direction"] == "short_only" and side != "short":
            continue
        if not in_session(idx[signal_i], config["session"]):
            continue
        if config["filter"] == "ema50_1h":
            e = ema1h[signal_i]
            if not np.isfinite(e):
                continue
            if (side == "long" and sig["signal_close"] <= e) or (
                side == "short" and sig["signal_close"] >= e
            ):
                continue

        entry = float(opens[entry_i])
        stop = sig["stop_line"]
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
            "signal_time": idx[signal_i], "entry_time": idx[entry_i],
            "exit_time": idx[exit_i], "side": side, "entry": entry,
            "stop": stop, "target": target, "exit": exit_price,
            "outcome": outcome, "gross_R": gross_r,
            "estimated_cost_R": cost_r, "net_R": gross_r - cost_r,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def write_monthly(trades, path):
    if trades.empty:
        return
    g = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"))
    g.groupby("month").agg(
        trades=("net_R", "size"),
        profitable_pct=("net_R", lambda x: float((x > 0).mean() * 100)),
        net_R=("net_R", "sum"),
    ).reset_index().to_csv(path, index=False)


def main():
    raw = fetch("15m")
    d, tr, hourly = prepare_base(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m history: {len(d)} rows")
    n = len(d)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    segments = {
        "train": (0, train_end),
        "validation": (train_end, validation_end),
        "oos": (validation_end, n),
    }
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
        "hourly_complete_bars": int(len(hourly)),
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    configs = []
    for source, atr_len, multiplier in itertools.product(
        SOURCES, ATR_LENGTHS, ATR_MULTIPLIERS
    ):
        signal_cache[(source, atr_len, multiplier)] = build_signals(
            d, tr, source, atr_len, multiplier
        )
    for source, atr_len, multiplier, target, filt, direction, session in itertools.product(
        SOURCES, ATR_LENGTHS, ATR_MULTIPLIERS, TARGETS_R,
        FILTERS, DIRECTIONS, SESSIONS
    ):
        cid = (
            f"{source}_atr{atr_len}_x{str(multiplier).replace('.', 'p')}_"
            f"{str(target).replace('.', 'p')}R_{filt}_{direction}_{session}"
        )
        configs.append({
            "config_id": cid, "source": source, "atr_length": atr_len,
            "atr_multiplier": multiplier, "target_r": target,
            "filter": filt, "direction": direction, "session": session,
            "signals": signal_cache[(source, atr_len, multiplier)],
        })

    train_rows, validation_rows = [], []
    for c in configs:
        base = {k: v for k, v in c.items() if k != "signals"}
        for sample in ("train", "validation"):
            trades = simulate(d, c["signals"], c, *segments[sample], gap_mask)
            row = base | {"sample": sample} | metrics(trades)
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
        eligible_train["train_quality"] = (
            eligible_train.net_R / eligible_train.max_drawdown_R.abs().clip(lower=1.0)
        )
        shortlist = eligible_train.sort_values(
            ["train_quality", "trades"], ascending=[False, False]
        ).head(MAX_TRAIN_CANDIDATES)
        eligible_validation = validation_df[
            validation_df.config_id.isin(shortlist.config_id)
            & (validation_df.trades >= MIN_VALIDATION_TRADES)
            & (validation_df.net_R > 0) & (validation_df.profit_factor >= 1.05)
            & (validation_df.max_drawdown_R >= -15.0)
            & (validation_df.positive_month_fraction >= 0.50)
        ].copy()
    else:
        shortlist, eligible_validation = pd.DataFrame(), pd.DataFrame()

    top_train = train_df.sort_values("net_R", ascending=False).head(5)
    top_validation = validation_df.sort_values("net_R", ascending=False).head(5)
    top_train.to_csv(OUT / "top_train.csv", index=False)
    top_validation.to_csv(OUT / "top_validation.csv", index=False)

    if not top_train.empty:
        cid = top_train.iloc[0].config_id
        c = next(x for x in configs if x["config_id"] == cid)
        tt = simulate(d, c["signals"], c, *segments["train"], gap_mask)
        vt = simulate(d, c["signals"], c, *segments["validation"], gap_mask)
        tt.to_csv(OUT / "best_train_trades.csv", index=False)
        vt.to_csv(OUT / "best_train_matching_validation_trades.csv", index=False)
        write_monthly(tt, OUT / "best_train_monthly.csv")
        write_monthly(vt, OUT / "best_train_matching_validation_monthly.csv")
    if not top_validation.empty:
        cid = top_validation.iloc[0].config_id
        c = next(x for x in configs if x["config_id"] == cid)
        vt = simulate(d, c["signals"], c, *segments["validation"], gap_mask)
        vt.to_csv(OUT / "best_validation_only_trades.csv", index=False)
        write_monthly(vt, OUT / "best_validation_only_monthly.csv")

    oos_summary = {}
    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = (
            eligible_validation.net_R / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        )
        selected = eligible_validation.sort_values(
            ["validation_quality", "trades"], ascending=[False, False]
        ).iloc[0]
        config = next(x for x in configs if x["config_id"] == selected.config_id)
        oos = simulate(d, config["signals"], config, *segments["oos"], gap_mask)
        oos.to_csv(OUT / "selected_oos_trades.csv", index=False)
        oos_summary = metrics(oos)
        pd.DataFrame([oos_summary | {"config_id": selected.config_id}]).to_csv(
            OUT / "selected_oos_summary.csv", index=False
        )
        write_monthly(oos, OUT / "selected_oos_monthly.csv")
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation funnel; OOS was not evaluated."
        )

    meta = {
        "matrix_configurations": len(configs),
        "train_eligible": int(len(eligible_train)),
        "train_shortlist": int(len(shortlist)),
        "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(not eligible_validation.empty),
        "oos_summary": oos_summary,
        "cost_assumption": "12bp round trip; actual fee tier unverified; no funding or separate spread/slippage model",
        "execution": "15m confirmed Supertrend flip; next-open entry; fixed signal-bar Supertrend-line stop; 1.5R/2R/3R target; 8h max hold; SL first; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train screen then validation screen; OOS once only for single validation-selected candidate",
        "indicator": "TradingView-style final-band recurrence with Wilder RMA ATR; source HL2 or 15m EMA50",
        "filter": "optional EMA50 on completed 1H candles only",
        "direction": "both, long-only, short-only",
        "sessions": "all hours or fixed UTC buckets; no DST adjustment",
    }
    (OUT / "methodology.json").write_text(json.dumps(meta, indent=2))

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"CONFIGURATIONS: {len(configs)}")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(shortlist)}; VALIDATION PASS: {len(eligible_validation)}")
    print("TOP TRAIN")
    print(top_train[[
        "config_id", "trades", "profitable_pct", "profit_factor", "net_R",
        "avg_R", "max_drawdown_R", "max_losing_streak", "positive_month_fraction",
    ]].to_string(index=False))
    print("TOP VALIDATION")
    print(top_validation[[
        "config_id", "trades", "profitable_pct", "profit_factor", "net_R",
        "avg_R", "max_drawdown_R", "max_losing_streak", "positive_month_fraction",
    ]].to_string(index=False))
    if eligible_validation.empty:
        print("NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; OOS WAS NOT EVALUATED.")
    else:
        print("SELECTED OOS SUMMARY")
        print(json.dumps(oos_summary, indent=2))
    print(f"Artifacts written to {OUT}/")


if __name__ == "__main__":
    main()
