"""Intraday BTCUSD 5m RSI extreme-reclaim mean-reversion research.

Signals use only completed 5m Wilder RSI values crossing back out of
oversold/overbought territory. Entries occur at the next 5m open; optional
1h EMA50 context uses only fully completed native 1h candles. Maximum hold
is 2h. OOS is evaluated once only after the fixed selection funnel passes.
"""
import hashlib
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT = Path("rsi_reversion_5m_results")
OUT.mkdir(exist_ok=True)
BASE = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL = "BTCUSD"
DAYS = 730
HEADERS = {"Accept": "application/json", "User-Agent": "SaltyQuantIntradayResearch/1.0"}
BAR = pd.Timedelta("5min")
MAX_HOLD_BARS = 24
COST_RATE = 0.0012
RSI_LENGTHS = (2, 5, 14)
THRESHOLDS = ((10, 90), (20, 80))
CONFIRMATIONS = ("rsi_crossback", "crossback_direction_candle")
STOPS = ("signal_extreme", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN_TRADES = 80
MIN_VALIDATION_TRADES = 30
MAX_TRAIN_CANDIDATES = 25


def fetch_candles(resolution, step_seconds, days):
    end = int(pd.Timestamp.now(tz="UTC").timestamp())
    start = end - days * 86400
    frames = []
    cursor = start
    chunk = step_seconds * 1800
    while cursor < end:
        stop = min(cursor + chunk, end)
        response = requests.get(
            BASE,
            params={"resolution": resolution, "symbol": SYMBOL, "start": cursor, "end": stop},
            headers=HEADERS,
            timeout=40,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is not True:
            raise RuntimeError(f"Delta API error for {resolution} candles: {payload}")
        rows = payload.get("result") or []
        if rows:
            frames.append(pd.DataFrame(rows))
        cursor = stop
        time.sleep(0.08)
    if not frames:
        raise RuntimeError(f"Delta returned no BTCUSD {resolution} candles")
    d = pd.concat(frames, ignore_index=True)
    d["timestamp"] = pd.to_datetime(pd.to_numeric(d["time"]), unit="s", utc=True)
    d = d.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    for col in ("open", "high", "low", "close"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d[
        (d.high >= d[["open", "close", "low"]].max(axis=1))
        & (d.low <= d[["open", "close", "high"]].min(axis=1))
    ]
    now = pd.Timestamp.now(tz="UTC")
    d = d[d.index + pd.Timedelta(seconds=step_seconds) <= now]
    if d.empty:
        raise RuntimeError(f"No closed BTCUSD {resolution} candles available")
    return d


def fetch_5m():
    return fetch_candles("5m", 300, DAYS)


def fetch_1h():
    return fetch_candles("1h", 3600, DAYS)


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


def prepare_data(raw, hourly_raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    previous = d.close.shift(1)
    true_range = pd.concat(
        [d.high - d.low, (d.high - previous).abs(), (d.low - previous).abs()],
        axis=1,
    ).max(axis=1)
    d["atr14"] = rma(true_range, 14)
    delta = d.close.diff().fillna(0.0)
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    for length in RSI_LENGTHS:
        avg_gain = rma(gains, length)
        avg_loss = rma(losses, length)
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi = rsi.mask(avg_loss.eq(0.0) & avg_gain.gt(0.0), 100.0)
        rsi = rsi.mask(avg_loss.eq(0.0) & avg_gain.eq(0.0), 50.0)
        d[f"rsi{length}"] = rsi

    # Use Delta's native 1h candles instead of resampling 5m data onto UTC
    # hour boundaries. The hourly EMA is exposed only after each 1h candle
    # has fully closed. Reset EMA warm-up after any missing-hour discontinuity.
    hourly = hourly_raw.sort_index().copy()
    hourly = hourly[~hourly.index.duplicated(keep="last")]
    hour_diff = hourly.index.to_series().diff()
    segment = hour_diff.ne(pd.Timedelta("1h")).cumsum()
    hourly["ema50"] = hourly.groupby(segment)["close"].transform(
        lambda values: values.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    available = hourly["ema50"].copy()
    available.index = available.index + pd.Timedelta("1h")
    d["ema50_1h"] = available.reindex(d.index, method="ffill")
    return d, true_range, hourly


def build_signals(d, rsi_length, thresholds, confirmation):
    rsi = d[f"rsi{rsi_length}"].to_numpy(dtype=float)
    atr = d.atr14.to_numpy(dtype=float)
    opens = d.open.to_numpy(dtype=float)
    highs = d.high.to_numpy(dtype=float)
    lows = d.low.to_numpy(dtype=float)
    closes = d.close.to_numpy(dtype=float)
    oversold, overbought = thresholds
    signals = []
    for i in range(1, len(d) - 1):
        if not np.isfinite(rsi[i - 1:i + 1]).all() or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        long_reclaim = rsi[i - 1] <= oversold and rsi[i] > oversold
        short_reclaim = rsi[i - 1] >= overbought and rsi[i] < overbought
        if confirmation == "crossback_direction_candle":
            long_reclaim = long_reclaim and closes[i] > opens[i]
            short_reclaim = short_reclaim and closes[i] < opens[i]
        if long_reclaim:
            side = "long"
        elif short_reclaim:
            side = "short"
        else:
            continue
        signals.append({
            "signal_i": i,
            "entry_i": i + 1,
            "side": side,
            "signal_extreme": float(lows[i] if side == "long" else highs[i]),
            "atr_signal": float(atr[i]),
            "signal_close": float(closes[i]),
        })
    return signals


def in_session(timestamp, session):
    if session == "all":
        return True
    lo, hi = {"07-19": (7, 19)}[session]
    return lo <= timestamp.hour < hi


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
    hourly_ema = d.ema50_1h.to_numpy(dtype=float)
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
        if config["filter"] == "ema50_1h":
            trend_ema = hourly_ema[signal_i]
            if not np.isfinite(trend_ema):
                continue
            if (side == "long" and signal["signal_close"] <= trend_ema) or (
                side == "short" and signal["signal_close"] >= trend_ema
            ):
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
    raw = fetch_5m()
    hourly_raw = fetch_1h()
    d, true_range, hourly = prepare_data(raw, hourly_raw)
    if len(d) < 50000:
        raise RuntimeError(f"Insufficient BTCUSD 5m history: {len(d)} rows")
    if len(hourly) < 1000:
        raise RuntimeError(f"Insufficient BTCUSD 1h context history: {len(hourly)} rows")
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
    # Validate adjacent intervals, not every timestamp against the first bar.
    # A single bad timestamp can shift the phase of all later bars and should
    # not cause the entire remaining history to be mislabeled off-cadence.
    off_grid_intervals = int((interval_seconds % 300 != 0).sum())
    max_off_grid_intervals = max(5, int(n * 0.001))
    if off_grid_intervals > max_off_grid_intervals:
        raise RuntimeError(
            f"Too many irregular 5m intervals: {off_grid_intervals} "
            f"(limit {max_off_grid_intervals}); inspect raw exchange timestamps"
        )
    hourly_differences = hourly.index.to_series().diff()
    hourly_gaps = int((hourly_differences.dropna() != pd.Timedelta("1h")).sum())

    data_path = OUT / "BTCUSD_5m.csv"
    hourly_path = OUT / "BTCUSD_1h.csv"
    d.to_csv(data_path)
    hourly.to_csv(hourly_path)
    data_quality = {
        "symbol": SYMBOL, "timeframe": "5m",
        "rows": int(n), "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps": int((differences.dropna() != BAR).sum()),
        "off_grid_intervals": off_grid_intervals,
        "hourly_complete_bars": int(len(hourly)),
        "hourly_gaps": hourly_gaps,
        "largest_gap_minutes": float(differences.dropna().max().total_seconds() / 60),
        "sha256_5m": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "sha256_1h": hashlib.sha256(hourly_path.read_bytes()).hexdigest(),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    configs = []
    for rsi_length, thresholds, confirmation in itertools.product(
        RSI_LENGTHS, THRESHOLDS, CONFIRMATIONS
    ):
        signal_cache[(rsi_length, thresholds, confirmation)] = build_signals(
            d, rsi_length, thresholds, confirmation
        )
    for rsi_length, thresholds, confirmation, stop, target, filt, direction, session in itertools.product(
        RSI_LENGTHS, THRESHOLDS, CONFIRMATIONS, STOPS, TARGETS_R,
        FILTERS, DIRECTIONS, SESSIONS
    ):
        lower, upper = thresholds
        config_id = (
            f"rsi{rsi_length}_{lower}-{upper}_{confirmation}_{stop}_"
            f"{str(target).replace('.', 'p')}R_{filt}_{direction}_{session}"
        )
        configs.append({
            "config_id": config_id,
            "rsi_length": rsi_length,
            "thresholds": thresholds,
            "confirmation": confirmation,
            "stop": stop,
            "target_r": target,
            "filter": filt,
            "direction": direction,
            "session": session,
            "signals": signal_cache[(rsi_length, thresholds, confirmation)],
        })

    train_rows, validation_rows = [], []
    for config in configs:
        base = {key: value for key, value in config.items() if key != "signals"}
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
        & (train_df.max_drawdown_R >= -35.0)
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
        & (shortlisted.max_drawdown_R >= -20.0)
        & (shortlisted.positive_month_fraction >= 0.50)
    ].copy()

    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = (
            eligible_validation.net_R / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        )
        selected = eligible_validation.sort_values(
            ["validation_quality", "profit_factor", "trades"],
            ascending=[False, False, False],
        ).iloc[0]
        selected_config = next(c for c in configs if c["config_id"] == selected.config_id)
        oos_trades = simulate(
            d, selected_config["signals"], selected_config,
            *segments["oos"], gap_mask
        )
        oos_row = {"config_id": selected.config_id, "sample": "oos"} | metrics(oos_trades)
        oos_trades.to_csv(OUT / "selected_oos_trades.csv", index=False)
        write_monthly(oos_trades, OUT / "selected_oos_monthly.csv")
        (OUT / "oos_evaluation.txt").write_text(
            "One validation-selected configuration evaluated once on OOS: "
            + selected.config_id + "\n"
        )
    else:
        oos_trades = pd.DataFrame()
        oos_row = {}
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation funnel; OOS was not evaluated.\n"
        )

    train_df.sort_values(["net_R", "profit_factor"], ascending=False).head(20).to_csv(OUT / "top_train.csv", index=False)
    validation_df.sort_values(["net_R", "profit_factor"], ascending=False).head(20).to_csv(OUT / "top_validation.csv", index=False)
    shortlisted.to_csv(OUT / "shortlist_validation.csv", index=False)
    (OUT / "methodology.json").write_text(json.dumps({
        "matrix_configurations": len(configs),
        "train_eligible": int(len(eligible_train)),
        "train_shortlist": int(len(shortlist)),
        "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(oos_row),
        "selected_oos": oos_row,
        "cost_assumption": "12bp round trip; actual fee tier unverified; no funding or separate spread/slippage model",
        "execution": "5m Wilder RSI(2/5/14) crossback from 10/90 or 20/80 extremes; compare crossback alone versus same-direction signal candle; next-open entry; signal-extreme+0.1ATR or 1.5ATR stop; 1.5R/2R/3R target; 2h max hold; SL first; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train screen then validation screen; OOS once only for single validation-selected candidate",
        "hourly_context": "EMA50 on fully completed 1h candles aggregated from 12 contiguous 5m bars",
        "sessions": "all hours or 07-19 UTC; assigned by actual next-bar entry time",
        "matrix_axes": {
            "rsi_length": list(RSI_LENGTHS),
            "thresholds": [list(x) for x in THRESHOLDS],
            "confirmation": list(CONFIRMATIONS),
            "stop": list(STOPS),
            "target_r": list(TARGETS_R),
            "filter": list(FILTERS),
            "direction": list(DIRECTIONS),
            "session": list(SESSIONS),
        },
        "limitations": "12bp round trip is an assumption; no funding or separate spread/slippage; fixed UTC bucket is not an exchange session definition; RSI extremes are a mechanical mean-reversion proxy; OHLC same-bar ambiguity resolves stop first"
    }, indent=2))

    for sample in ("train", "validation"):
        frame = train_df if sample == "train" else validation_df
        best = frame.sort_values(["net_R", "profit_factor"], ascending=False).iloc[0]
        config = next(c for c in configs if c["config_id"] == best.config_id)
        trades = simulate(d, config["signals"], config, *segments[sample], gap_mask)
        trades.to_csv(OUT / f"best_{sample}_trades.csv", index=False)
        write_monthly(trades, OUT / f"best_{sample}_monthly.csv")

    if not shortlist.empty:
        best_id = shortlist.iloc[0].config_id
        config = next(c for c in configs if c["config_id"] == best_id)
        matching = simulate(d, config["signals"], config, *segments["validation"], gap_mask)
        matching.to_csv(OUT / "best_train_matching_validation_trades.csv", index=False)
        write_monthly(matching, OUT / "best_train_matching_validation_monthly.csv")

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"MATRIX: {len(configs)} configurations")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(shortlist)}; VALIDATION PASS: {len(eligible_validation)}")
    print("TOP TRAIN")
    print(train_df.sort_values(["net_R", "profit_factor"], ascending=False).head(10).to_string(index=False))
    print("TOP VALIDATION")
    print(validation_df.sort_values(["net_R", "profit_factor"], ascending=False).head(10).to_string(index=False))
    if oos_row:
        print("SELECTED OOS")
        print(pd.DataFrame([oos_row]).to_string(index=False))
    else:
        print("NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; OOS WAS NOT EVALUATED.")


if __name__ == "__main__":
    main()

# Triggered reproducible CI after workflow definition was added.
