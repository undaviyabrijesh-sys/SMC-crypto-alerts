"""Intraday BTCUSD Bollinger/Keltner squeeze-breakout research.

A completed 15m bar can signal only after a prior run of at least four
completed squeeze bars has ended within the previous eight bars. The close
must break the prior Donchian high/low. Entry is the next 15m open.
Each trade is capped at 8h. OOS is evaluated once only if the preregistered
train/validation funnel selects a candidate.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("squeeze_breakout_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_RATE = 0.0012
KC_MULTIPLIERS = (1.5, 2.0)
DONCHIAN_LENGTHS = (20, 40)
STOPS = ("signal_extreme", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-13", "13-19")
MIN_SQUEEZE_BARS = 4
MAX_BARS_AFTER_RELEASE = 8
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
    prev = d.close.shift(1)
    tr = pd.concat(
        [d.high - d.low, (d.high - prev).abs(), (d.low - prev).abs()],
        axis=1,
    ).max(axis=1)
    d["atr14"] = rma(tr, 14)
    d["ema20"] = d.close.ewm(span=20, adjust=False, min_periods=20).mean()
    d["bb_mid"] = d.close.rolling(20, min_periods=20).mean()
    bb_std = d.close.rolling(20, min_periods=20).std(ddof=0)
    d["bb_upper"] = d.bb_mid + 2.0 * bb_std
    d["bb_lower"] = d.bb_mid - 2.0 * bb_std

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    # Completed hourly values become visible at their right-edge timestamp.
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    return d, tr, hourly


def build_squeeze_and_signals(d, tr, kc_mult, donchian_length):
    atr = d.atr14.to_numpy(dtype=float)
    ema = d.ema20.to_numpy(dtype=float)
    bb_u = d.bb_upper.to_numpy(dtype=float)
    bb_l = d.bb_lower.to_numpy(dtype=float)
    close = d.close.to_numpy(dtype=float)
    high = d.high.to_numpy(dtype=float)
    low = d.low.to_numpy(dtype=float)
    idx = d.index

    kc_u = ema + kc_mult * atr
    kc_l = ema - kc_mult * atr
    squeeze = np.isfinite(bb_u) & np.isfinite(bb_l) & np.isfinite(kc_u) & np.isfinite(kc_l)
    squeeze &= (bb_u < kc_u) & (bb_l > kc_l)

    prior_high = d.high.rolling(donchian_length, min_periods=donchian_length).max().shift(1).to_numpy(dtype=float)
    prior_low = d.low.rolling(donchian_length, min_periods=donchian_length).min().shift(1).to_numpy(dtype=float)

    signals = []
    run_length = 0
    last_squeeze_end = -1
    last_squeeze_length = 0
    for i in range(1, len(d) - 1):
        if squeeze[i]:
            run_length += 1
            continue

        if run_length:
            # The latest completed squeeze run supersedes any older run,
            # even when the latest run is too short to qualify.
            last_squeeze_end = i - 1
            last_squeeze_length = run_length
            run_length = 0

        bars_after_release = i - last_squeeze_end
        if (
            last_squeeze_length < MIN_SQUEEZE_BARS
            or bars_after_release < 1
            or bars_after_release > MAX_BARS_AFTER_RELEASE
            or not np.isfinite(prior_high[i] + prior_low[i] + atr[i])
            or atr[i] <= 0
        ):
            continue

        side = None
        if close[i] > prior_high[i]:
            side = "long"
        elif close[i] < prior_low[i]:
            side = "short"
        if side is None:
            continue

        signals.append({
            "signal_i": i,
            "entry_i": i + 1,
            "side": side,
            "signal_extreme": float(low[i] if side == "long" else high[i]),
            "atr_signal": float(atr[i]),
            "squeeze_length": int(last_squeeze_length),
            "bars_after_release": int(bars_after_release),
            "donchian_level": float(prior_high[i] if side == "long" else prior_low[i]),
            "signal_close": float(close[i]),
            "signal_time": idx[i],
        })
        # Consume the squeeze release: no repeated signals from the same squeeze.
        last_squeeze_end = -1
        last_squeeze_length = 0
    return squeeze, signals


def in_session(ts, session):
    if session == "all":
        return True
    lo, hi = {"07-13": (7, 13), "13-19": (13, 19)}[session]
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
        if not in_session(idx[entry_i], config["session"]):
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
        if config["stop"] == "signal_extreme":
            buffer = 0.1 * sig["atr_signal"]
            stop = sig["signal_extreme"] - buffer if side == "long" else sig["signal_extreme"] + buffer
        else:
            distance = 1.5 * sig["atr_signal"]
            stop = entry - distance if side == "long" else entry + distance

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
                # Fixed target fill; no favourable gap improvement.
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
            "squeeze_length": sig["squeeze_length"],
            "bars_after_release": sig["bars_after_release"],
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
    d, tr, hourly = prepare_data(raw)
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
    for kc_mult, donchian_length in itertools.product(KC_MULTIPLIERS, DONCHIAN_LENGTHS):
        signal_cache[(kc_mult, donchian_length)] = build_squeeze_and_signals(
            d, tr, kc_mult, donchian_length
        )[1]

    for kc_mult, donchian_length, stop, target, filt, direction, session in itertools.product(
        KC_MULTIPLIERS, DONCHIAN_LENGTHS, STOPS, TARGETS_R,
        FILTERS, DIRECTIONS, SESSIONS
    ):
        cid = (
            f"kc{str(kc_mult).replace('.', 'p')}_dc{donchian_length}_"
            f"{stop}_{str(target).replace('.', 'p')}R_{filt}_{direction}_{session}"
        )
        configs.append({
            "config_id": cid, "kc_multiplier": kc_mult,
            "donchian_length": donchian_length, "stop": stop,
            "target_r": target, "filter": filt,
            "direction": direction, "session": session,
            "signals": signal_cache[(kc_mult, donchian_length)],
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
            ["train_quality", "profit_factor", "trades"],
            ascending=[False, False, False],
        ).head(MAX_TRAIN_CANDIDATES)
    else:
        shortlist = eligible_train

    validation_map = validation_df.set_index("config_id")
    shortlisted_rows = []
    for _, row in shortlist.iterrows():
        v = validation_map.loc[row.config_id]
        shortlisted_rows.append(v)
    shortlisted = pd.DataFrame(shortlisted_rows) if shortlisted_rows else pd.DataFrame(columns=validation_df.columns)

    eligible_validation = shortlisted[
        (shortlisted.trades >= MIN_VALIDATION_TRADES)
        & (shortlisted.net_R > 0)
        & (shortlisted.profit_factor >= 1.05)
        & (shortlisted.max_drawdown_R >= -15.0)
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
        oos_trades = simulate(d, selected_config["signals"], selected_config, *segments["oos"], gap_mask)
        oos_row = {"config_id": selected.config_id, "sample": "oos"} | metrics(oos_trades)
        oos_trades.to_csv(OUT / "selected_oos_trades.csv", index=False)
        write_monthly(oos_trades, OUT / "selected_oos_monthly.csv")
        (OUT / "oos_evaluation.txt").write_text(
            "One validation-selected configuration evaluated once on OOS: "
            + selected.config_id + "\\n"
        )
    else:
        oos_trades = pd.DataFrame()
        oos_row = {}
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation funnel; OOS was not evaluated.\\n"
        )

    train_df.sort_values(["net_R", "profit_factor"], ascending=False).head(20).to_csv(OUT / "top_train.csv", index=False)
    validation_df.sort_values(["net_R", "profit_factor"], ascending=False).head(20).to_csv(OUT / "top_validation.csv", index=False)
    (OUT / "shortlist_validation.csv").write_text(shortlisted.to_csv(index=False))
    (OUT / "methodology.json").write_text(json.dumps({
        "matrix_configurations": len(configs),
        "train_eligible": int(len(eligible_train)),
        "train_shortlist": int(len(shortlist)),
        "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(oos_row),
        "selected_oos": oos_row,
        "cost_assumption": "12bp round trip; actual fee tier unverified; no funding or separate spread/slippage model",
        "execution": "15m breakout after >=4-bar BB(20,2) inside KC(EMA20 +/- 1.5/2.0 ATR14) squeeze ended within 8 bars; prior 20/40-bar Donchian close break; next-open entry; signal-extreme+0.1ATR or 1.5ATR stop; 1.5R/2R/3R target; 8h max hold; SL first; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train screen then validation screen; OOS once only for single validation-selected candidate",
        "squeeze": "BB(20,2) inside Keltner EMA20 +/- KC multiplier*Wilder ATR14; min 4 consecutive completed bars; first breakout signal within 8 bars after squeeze run ends; one signal per squeeze run",
        "filter": "optional completed-1H EMA50 only",
        "sessions": "all, 07-13 UTC, 13-19 UTC; assigned by actual next-bar entry time",
        "matrix_axes": {
            "kc_multiplier": list(KC_MULTIPLIERS),
            "donchian_length": list(DONCHIAN_LENGTHS),
            "stop": list(STOPS),
            "target_r": list(TARGETS_R),
            "filter": list(FILTERS),
            "direction": list(DIRECTIONS),
            "session": list(SESSIONS)
        },
        "limitations": "Delta exchange candle volume is not used; no funding or separate spread/slippage; fixed UTC buckets are not exchange session definitions; OHLC same-bar ambiguity resolves stop first"
    }, indent=2))

    for name, frame in (("best_train", train_df), ("best_validation", validation_df)):
        if frame.empty:
            continue
        best = frame.sort_values(["net_R", "profit_factor"], ascending=False).iloc[0]
        config = next(c for c in configs if c["config_id"] == best.config_id)
        sample = name.replace("best_", "")
        trades = simulate(d, config["signals"], config, *segments[sample], gap_mask)
        trades.to_csv(OUT / f"{name}_trades.csv", index=False)
        write_monthly(trades, OUT / f"{name}_monthly.csv")

    if not shortlisted.empty:
        best_train_id = shortlist.iloc[0].config_id
        best_train_config = next(c for c in configs if c["config_id"] == best_train_id)
        matching_validation = simulate(
            d, best_train_config["signals"], best_train_config,
            *segments["validation"], gap_mask
        )
        matching_validation.to_csv(OUT / "best_train_matching_validation_trades.csv", index=False)
        write_monthly(matching_validation, OUT / "best_train_matching_validation_monthly.csv")

    print(f"DATA QUALITY\\n{json.dumps(data_quality, indent=2)}")
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
