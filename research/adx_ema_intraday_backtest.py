"""Intraday BTCUSD ADX + EMA pullback continuation research.

Signals use completed 15m pullback/reclaim candles, directional DMI alignment,
an ADX strength threshold, and optionally rising ADX. A completed 1h EMA50/200
regime filter is optional. Entries are next 15m open; max hold is 8 hours.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("adx_ema_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_RATE = 0.0012
EMA_LENGTHS = (20, 50)
ADX_THRESHOLDS = (15.0, 20.0, 25.0)
ADX_RISING = (False, True)
CONFIRMATIONS = ("ema_reclaim", "break_previous")
STOPS = ("signal_extreme", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
HTF_FILTERS = ("none", "ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
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
        else:
            out[i] = np.nan
    return pd.Series(out, index=series.index)


def prepare_data(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    differences = d.index.to_series().diff()
    d["segment"] = differences.ne(BAR).cumsum().astype(int)

    # Calculate all 15m indicators independently inside contiguous segments.
    previous_close = d.groupby("segment").close.shift(1)
    tr = pd.concat(
        [
            d.high - d.low,
            (d.high - previous_close).abs(),
            (d.low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr14"] = d.groupby("segment", group_keys=False).apply(
        lambda g: rma(tr.loc[g.index], 14), include_groups=False
    ).reset_index(level=0, drop=True) if False else np.nan
    # Explicit per-segment assignment avoids cross-gap indicator carry.
    for _, g in d.groupby("segment", sort=False):
        idx = g.index
        d.loc[idx, "atr14"] = rma(tr.loc[idx], 14).to_numpy()
        for length in EMA_LENGTHS:
            d.loc[idx, f"ema{length}"] = g.close.ewm(
                span=length, adjust=False, min_periods=length
            ).mean().to_numpy()

    up_move = d.groupby("segment").high.diff().fillna(0.0)
    down_move = (-d.groupby("segment").low.diff()).fillna(0.0)
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0.0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0.0), 0.0)
    d["plus_di"] = np.nan
    d["minus_di"] = np.nan
    d["adx14"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        idx = g.index
        atr = d.loc[idx, "atr14"]
        plus_smoothed = rma(plus_dm.loc[idx], 14)
        minus_smoothed = rma(minus_dm.loc[idx], 14)
        plus_di = 100.0 * plus_smoothed / atr.replace(0.0, np.nan)
        minus_di = 100.0 * minus_smoothed / atr.replace(0.0, np.nan)
        denom = (plus_di + minus_di).replace(0.0, np.nan)
        dx = (100.0 * (plus_di - minus_di).abs() / denom).fillna(0.0)
        d.loc[idx, "plus_di"] = plus_di.to_numpy()
        d.loc[idx, "minus_di"] = minus_di.to_numpy()
        d.loc[idx, "adx14"] = rma(dx, 14).to_numpy()

    # Build only complete 1h candles from four contiguous 15m bars.
    hourly = d[["open", "high", "low", "close"]].resample(
        "1h", label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    hourly_segment = hourly.index.to_series().diff().ne(pd.Timedelta("1h")).cumsum()
    hourly["ema50"] = hourly.groupby(hourly_segment).close.transform(
        lambda x: x.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    hourly["ema200"] = hourly.groupby(hourly_segment).close.transform(
        lambda x: x.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    # Right-edge timestamps mean these values become available only after
    # the hourly candle has closed. Forward-fill to subsequent 15m bars.
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    d["ema200_1h"] = hourly.ema200.reindex(d.index, method="ffill")
    return d, tr, hourly


def build_signals(d, ema_length, adx_threshold, adx_rising, confirmation):
    ema = d[f"ema{ema_length}"].to_numpy(dtype=float)
    adx = d.adx14.to_numpy(dtype=float)
    plus_di = d.plus_di.to_numpy(dtype=float)
    minus_di = d.minus_di.to_numpy(dtype=float)
    atr = d.atr14.to_numpy(dtype=float)
    opens = d.open.to_numpy(dtype=float)
    highs = d.high.to_numpy(dtype=float)
    lows = d.low.to_numpy(dtype=float)
    closes = d.close.to_numpy(dtype=float)
    signals = []

    for i in range(1, len(d) - 1):
        if d.segment.iloc[i] != d.segment.iloc[i - 1]:
            continue
        if not np.isfinite([ema[i], adx[i], plus_di[i], minus_di[i], atr[i]]).all():
            continue
        if adx[i] < adx_threshold:
            continue
        if adx_rising and (not np.isfinite(adx[i - 3]) or adx[i] <= adx[i - 3]):
            continue

        long_base = lows[i] <= ema[i] and closes[i] > opens[i]
        short_base = highs[i] >= ema[i] and closes[i] < opens[i]
        if confirmation == "ema_reclaim":
            long_signal = long_base and closes[i] > ema[i]
            short_signal = short_base and closes[i] < ema[i]
        else:
            long_signal = long_base and closes[i] > highs[i - 1]
            short_signal = short_base and closes[i] < lows[i - 1]

        side = None
        if long_signal and plus_di[i] > minus_di[i]:
            side = "long"
        elif short_signal and minus_di[i] > plus_di[i]:
            side = "short"
        if side is None:
            continue

        signals.append({
            "signal_i": i,
            "entry_i": i + 1,
            "side": side,
            "signal_extreme": float(lows[i] if side == "long" else highs[i]),
            "atr_signal": float(atr[i]),
            "signal_close": float(closes[i]),
            "adx": float(adx[i]),
            "plus_di": float(plus_di[i]),
            "minus_di": float(minus_di[i]),
        })
    return signals


def in_session(timestamp, session):
    if session == "all":
        return True
    return 7 <= timestamp.hour < 19


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
    returns = g.net_R.astype(float)
    wins, losses = returns[returns > 0], returns[returns < 0]
    equity = returns.cumsum().to_numpy()
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    drawdown = equity - peaks
    monthly = g.assign(month=g.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(g)),
        "profitable_pct": round(float((returns > 0).mean() * 100), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) else None,
        "net_R": round(float(returns.sum()), 2),
        "avg_R": round(float(returns.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, drawdown.min())), 2),
        "max_losing_streak": int(max_losing_streak(returns.to_numpy())),
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
    ema50_1h = d.ema50_1h.to_numpy(dtype=float)
    ema200_1h = d.ema200_1h.to_numpy(dtype=float)
    index = d.index
    rows = []
    last_exit = -1

    for signal in signals:
        signal_i, entry_i = signal["signal_i"], signal["entry_i"]
        if entry_i < start_i or entry_i >= end_i or entry_i <= last_exit:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if gap_mask[signal_i:entry_i + MAX_HOLD_BARS].any():
            continue

        side = signal["side"]
        if config["direction"] == "long_only" and side != "long":
            continue
        if config["direction"] == "short_only" and side != "short":
            continue
        if not in_session(index[entry_i], config["session"]):
            continue
        if config["htf_filter"] == "ema50_200":
            e50, e200 = ema50_1h[signal_i], ema200_1h[signal_i]
            if not np.isfinite(e50) or not np.isfinite(e200):
                continue
            if (side == "long" and e50 <= e200) or (side == "short" and e50 >= e200):
                continue

        entry = float(opens[entry_i])
        if config["stop"] == "signal_extreme":
            buffer = 0.1 * signal["atr_signal"]
            stop = (
                signal["signal_extreme"] - buffer
                if side == "long"
                else signal["signal_extreme"] + buffer
            )
        else:
            distance = 1.5 * signal["atr_signal"]
            stop = entry - distance if side == "long" else entry + distance

        risk = entry - stop if side == "long" else stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = (
            entry + config["target_r"] * risk
            if side == "long"
            else entry - config["target_r"] * risk
        )

        outcome = "TIME"
        exit_i = entry_i + MAX_HOLD_BARS - 1
        exit_price = float(closes[exit_i])
        for j in range(entry_i, entry_i + MAX_HOLD_BARS):
            stop_hit = lows[j] <= stop if side == "long" else highs[j] >= stop
            target_hit = highs[j] >= target if side == "long" else lows[j] <= target
            if stop_hit:
                outcome = "SL"
                exit_price = (
                    min(stop, float(opens[j]))
                    if side == "long"
                    else max(stop, float(opens[j]))
                )
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
        cost_r = entry * COST_RATE / risk
        rows.append({
            "signal_time": index[signal_i],
            "entry_time": index[entry_i],
            "exit_time": index[exit_i],
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "outcome": outcome,
            "adx": signal["adx"],
            "plus_di": signal["plus_di"],
            "minus_di": signal["minus_di"],
            "gross_R": gross_r,
            "estimated_cost_R": cost_r,
            "net_R": gross_r - cost_r,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def write_monthly(trades, path):
    if trades.empty:
        return
    grouped = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"))
    grouped.groupby("month").agg(
        trades=("net_R", "size"),
        profitable_pct=("net_R", lambda x: float((x > 0).mean() * 100)),
        net_R=("net_R", "sum"),
    ).reset_index().to_csv(path, index=False)


def main():
    raw = fetch("15m")
    d, true_range, hourly = prepare_data(raw)
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
    differences = d.index.to_series().diff()
    gap_mask = differences.ne(BAR).to_numpy(copy=True)
    gap_mask[0] = False
    interval_seconds = differences.dropna().dt.total_seconds()
    off_grid = int((interval_seconds % 900 != 0).sum())
    if off_grid > max(5, int(n * 0.001)):
        raise RuntimeError(f"Too many off-grid 15m intervals: {off_grid}")

    data_path = OUT / "BTCUSD_15m.csv"
    hourly_path = OUT / "BTCUSD_1h_complete.csv"
    d.to_csv(data_path)
    hourly.to_csv(hourly_path)
    data_quality = {
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "rows": int(n),
        "start_utc": str(d.index.min()),
        "end_utc": str(d.index.max()),
        "gaps": int((differences.dropna() != BAR).sum()),
        "off_grid_intervals": off_grid,
        "hourly_complete_bars": int(len(hourly)),
        "hourly_gaps": int((hourly.index.to_series().diff().dropna() != pd.Timedelta("1h")).sum()),
        "sha256_15m": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "sha256_1h": hashlib.sha256(hourly_path.read_bytes()).hexdigest(),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    for ema_length, threshold, rising, confirmation in itertools.product(
        EMA_LENGTHS, ADX_THRESHOLDS, ADX_RISING, CONFIRMATIONS
    ):
        key = (ema_length, threshold, rising, confirmation)
        signal_cache[key] = build_signals(d, ema_length, threshold, rising, confirmation)

    configs = []
    for ema_length, threshold, rising, confirmation, stop, target, htf, direction, session in itertools.product(
        EMA_LENGTHS, ADX_THRESHOLDS, ADX_RISING, CONFIRMATIONS, STOPS,
        TARGETS_R, HTF_FILTERS, DIRECTIONS, SESSIONS
    ):
        cid = (
            f"ema{ema_length}_adx{int(threshold)}_rising{int(rising)}_"
            f"{confirmation}_{stop}_{str(target).replace('.', 'p')}R_"
            f"{htf}_{direction}_{session}"
        )
        configs.append({
            "config_id": cid,
            "ema_length": ema_length,
            "adx_threshold": threshold,
            "adx_rising": rising,
            "confirmation": confirmation,
            "stop": stop,
            "target_r": target,
            "htf_filter": htf,
            "direction": direction,
            "session": session,
            "signals": signal_cache[(ema_length, threshold, rising, confirmation)],
        })

    train_rows, validation_rows = [], []
    for config in configs:
        base = {k: v for k, v in config.items() if k != "signals"}
        for sample in ("train", "validation"):
            trades = simulate(d, config["signals"], config, *segments[sample], gap_mask)
            row = base | {"sample": sample} | metrics(trades)
            (train_rows if sample == "train" else validation_rows).append(row)

    train_df = pd.DataFrame(train_rows)
    validation_df = pd.DataFrame(validation_rows)
    train_df.to_csv(OUT / "train_summary.csv", index=False)
    validation_df.to_csv(OUT / "validation_summary.csv", index=False)

    eligible_train = train_df[
        (train_df.trades >= MIN_TRAIN_TRADES)
        & (train_df.net_R > 0)
        & (train_df.profit_factor >= 1.05)
        & (train_df.max_drawdown_R >= -25.0)
    ].copy()
    if not eligible_train.empty:
        eligible_train["train_quality"] = (
            eligible_train.net_R / eligible_train.max_drawdown_R.abs().clip(lower=1.0)
        )
        shortlist = eligible_train.sort_values(
            ["train_quality", "profit_factor", "trades"],
            ascending=[False, False, False],
        ).head(MAX_TRAIN_CANDIDATES)
    else:
        shortlist = eligible_train

    validation_map = validation_df.set_index("config_id")
    shortlist_rows = [
        validation_map.loc[row.config_id]
        for _, row in shortlist.iterrows()
    ]
    shortlisted = (
        pd.DataFrame(shortlist_rows)
        if shortlist_rows
        else pd.DataFrame(columns=validation_df.columns)
    )
    eligible_validation = shortlisted[
        (shortlisted.trades >= MIN_VALIDATION_TRADES)
        & (shortlisted.net_R > 0)
        & (shortlisted.profit_factor >= 1.05)
        & (shortlisted.max_drawdown_R >= -15.0)
        & (shortlisted.positive_month_fraction >= 0.50)
    ].copy()

    # Exclude zero-trade rows from descriptive leaderboards; a flat zero is
    # not a strategy result and must not outrank every losing configuration.
    nonzero_train = train_df[train_df.trades > 0].copy()
    nonzero_validation = validation_df[validation_df.trades > 0].copy()
    top_train = nonzero_train.sort_values(
        ["net_R", "profit_factor"], ascending=[False, False]
    ).head(20)
    top_validation = nonzero_validation.sort_values(
        ["net_R", "profit_factor"], ascending=[False, False]
    ).head(20)
    top_train.to_csv(OUT / "top_train_nonzero.csv", index=False)
    top_validation.to_csv(OUT / "top_validation_nonzero.csv", index=False)
    shortlisted.to_csv(OUT / "shortlist_validation.csv", index=False)

    if not top_train.empty:
        cid = top_train.iloc[0].config_id
        config = next(c for c in configs if c["config_id"] == cid)
        train_trades = simulate(d, config["signals"], config, *segments["train"], gap_mask)
        matching_validation = simulate(
            d, config["signals"], config, *segments["validation"], gap_mask
        )
        train_trades.to_csv(OUT / "best_train_nonzero_trades.csv", index=False)
        matching_validation.to_csv(OUT / "best_train_matching_validation_trades.csv", index=False)
        write_monthly(train_trades, OUT / "best_train_nonzero_monthly.csv")
        write_monthly(matching_validation, OUT / "best_train_matching_validation_monthly.csv")

    if not top_validation.empty:
        cid = top_validation.iloc[0].config_id
        config = next(c for c in configs if c["config_id"] == cid)
        validation_trades = simulate(
            d, config["signals"], config, *segments["validation"], gap_mask
        )
        validation_trades.to_csv(OUT / "best_validation_nonzero_trades.csv", index=False)
        write_monthly(validation_trades, OUT / "best_validation_nonzero_monthly.csv")

    oos_summary = {}
    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = (
            eligible_validation.net_R / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        )
        selected = eligible_validation.sort_values(
            ["validation_quality", "profit_factor", "trades"],
            ascending=[False, False, False],
        ).iloc[0]
        config = next(c for c in configs if c["config_id"] == selected.config_id)
        oos_trades = simulate(d, config["signals"], config, *segments["oos"], gap_mask)
        oos_trades.to_csv(OUT / "selected_oos_trades.csv", index=False)
        write_monthly(oos_trades, OUT / "selected_oos_monthly.csv")
        oos_summary = metrics(oos_trades)
        (OUT / "oos_evaluation.txt").write_text(
            "One validation-selected configuration evaluated once on OOS: "
            + selected.config_id + "\n"
        )
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation funnel; OOS was not evaluated.\n"
        )

    methodology = {
        "matrix_configurations": len(configs),
        "train_eligible": int(len(eligible_train)),
        "shortlisted": int(len(shortlist)),
        "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(oos_summary),
        "oos_summary": oos_summary,
        "cost_assumption": "12bp round trip; actual fee tier unverified; no funding or separate spread/slippage model",
        "execution": "15m EMA20/50 pullback touch/reclaim or break of prior candle extreme; Wilder ADX14 threshold 15/20/25; +DI/-DI directional alignment; optional ADX rising over 3 bars; next-open entry; signal-extreme+0.1ATR or 1.5ATR stop; 1.5R/2R/3R target; 8h max hold; SL first; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train screen then validation screen; OOS once only for single validation-selected candidate",
        "hourly_context": "optional completed 1h EMA50/EMA200 regime alignment; only full 4x15m hours; EMA values exposed after hourly close",
        "sessions": "all hours or 07:00-19:00 UTC; assigned by actual next-bar entry time",
        "matrix_axes": {
            "ema_length": list(EMA_LENGTHS),
            "adx_threshold": list(ADX_THRESHOLDS),
            "adx_rising": list(ADX_RISING),
            "confirmation": list(CONFIRMATIONS),
            "stop": list(STOPS),
            "target_r": list(TARGETS_R),
            "htf_filter": list(HTF_FILTERS),
            "direction": list(DIRECTIONS),
            "session": list(SESSIONS),
        },
        "limitations": "12bp round trip is assumed, not fee-tier verified; no funding or separate spread/slippage; fixed UTC session proxy; mechanical DMI/ADX/EMA definition; OHLC same-bar ambiguity resolves stop first",
    }
    (OUT / "methodology.json").write_text(json.dumps(methodology, indent=2))

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"MATRIX: {len(configs)} configurations")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(shortlist)}; VALIDATION PASS: {len(eligible_validation)}")
    print("TOP NONZERO TRAIN")
    if top_train.empty:
        print("No trades")
    else:
        print(top_train[[
            "config_id", "trades", "profitable_pct", "profit_factor", "net_R",
            "avg_R", "max_drawdown_R", "max_losing_streak", "positive_month_fraction",
        ]].head(10).to_string(index=False))
    print("TOP NONZERO VALIDATION")
    if top_validation.empty:
        print("No trades")
    else:
        print(top_validation[[
            "config_id", "trades", "profitable_pct", "profit_factor", "net_R",
            "avg_R", "max_drawdown_R", "max_losing_streak", "positive_month_fraction",
        ]].head(10).to_string(index=False))
    if oos_summary:
        print("SELECTED OOS")
        print(json.dumps(oos_summary, indent=2))
    else:
        print("NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; OOS WAS NOT EVALUATED.")


if __name__ == "__main__":
    main()
