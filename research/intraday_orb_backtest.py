"""Intraday BTCUSD UTC opening-range breakout research.

Each UTC block has a one-hour opening range (four completed 15m bars).
The first 15m close outside that range, optionally beyond an ATR buffer,
is the breakout signal; entry is the following 15m open. The setup is
strictly intraday: max 8h holding, one trade at a time per configuration.
No parameter is selected using OOS.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("intraday_orb_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_RATE = 0.0012
ANCHORS = (0, 7, 13, 19)
BUFFERS_ATR = (0.0, 0.1)
STOPS = ("opposite_range", "breakout_candle", "atr1", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0, 4.0)
FILTERS = ("none", "ema50_1h_trend")
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
    d["atr15"] = rma(tr, 14)

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    h_count = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[h_count.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    # A 1H value is available only at its right-edge close timestamp.
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    return d, hourly


def build_signals(d, anchor_hour, buffer_atr):
    idx = d.index
    op = d.open.to_numpy(dtype=float)
    hi = d.high.to_numpy(dtype=float)
    lo = d.low.to_numpy(dtype=float)
    cl = d.close.to_numpy(dtype=float)
    atr = d.atr15.to_numpy(dtype=float)
    signals = []

    first_day = idx.min().normalize()
    last_day = idx.max().normalize()
    days = pd.date_range(first_day, last_day, freq="1D", tz="UTC")
    for day in days:
        start_ts = day + pd.Timedelta(hours=anchor_hour)
        next_anchor = ANCHORS[(ANCHORS.index(anchor_hour) + 1) % len(ANCHORS)]
        end_day = day if next_anchor > anchor_hour else day + pd.Timedelta(days=1)
        end_ts = end_day + pd.Timedelta(hours=next_anchor)
        start = int(idx.searchsorted(start_ts, side="left"))
        end = int(idx.searchsorted(end_ts, side="left"))
        if start >= len(idx) or idx[start] != start_ts:
            continue
        # Require exactly four contiguous 15m opening-range candles.
        range_ids = np.arange(start, start + 4)
        if range_ids[-1] >= len(idx):
            continue
        if not np.array_equal(idx[range_ids].asi8, (start_ts + np.arange(4) * BAR).asi8):
            continue
        if start + 4 >= end or end > len(idx):
            continue
        range_high = float(np.max(hi[range_ids]))
        range_low = float(np.min(lo[range_ids]))
        if not np.isfinite(range_high + range_low) or range_high <= range_low:
            continue

        # First confirmed close outside the completed range in this UTC block.
        for i in range(start + 4, min(end - 1, len(idx) - 1)):
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            pad = buffer_atr * atr[i]
            side = None
            if cl[i] > range_high + pad:
                side = "long"
            elif cl[i] < range_low - pad:
                side = "short"
            if side is None:
                continue
            entry_i = i + 1
            if entry_i >= end:
                break
            signals.append({
                "signal_i": i,
                "entry_i": entry_i,
                "side": side,
                "range_high": range_high,
                "range_low": range_low,
                "signal_extreme": float(lo[i] if side == "long" else hi[i]),
                "atr_signal": float(atr[i]),
                "anchor_hour": int(anchor_hour),
                "session_date": str(day.date()),
            })
            break
    return signals


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
    ema = d.ema50_1h.to_numpy(dtype=float)
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
        if config["filter"] == "ema50_1h_trend":
            e = ema[signal_i]
            if not np.isfinite(e):
                continue
            if (side == "long" and closes[signal_i] <= e) or (
                side == "short" and closes[signal_i] >= e
            ):
                continue

        entry = float(opens[entry_i])
        if config["stop"] == "opposite_range":
            stop = sig["range_low"] if side == "long" else sig["range_high"]
        elif config["stop"] == "breakout_candle":
            pad = 0.1 * sig["atr_signal"]
            stop = sig["signal_extreme"] - pad if side == "long" else sig["signal_extreme"] + pad
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
                # No favourable gap improvement: fill at the fixed target.
                exit_price = target
                exit_i = j
                break

        gross_r = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        cost_r = entry * COST_RATE / risk
        rows.append({
            "entry_time": idx[entry_i], "exit_time": idx[exit_i], "side": side,
            "anchor_hour_utc": sig["anchor_hour"], "session_date": sig["session_date"],
            "entry": entry, "stop": stop, "target": target, "exit": exit_price,
            "outcome": outcome, "gross_R": gross_r, "estimated_cost_R": cost_r,
            "net_R": gross_r - cost_r,
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
    d, hourly = prepare_data(raw)
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
    for anchor, buffer_atr in itertools.product(ANCHORS, BUFFERS_ATR):
        signal_cache[(anchor, buffer_atr)] = build_signals(d, anchor, buffer_atr)
    for anchor, buffer_atr, stop, target, filt in itertools.product(
        ANCHORS, BUFFERS_ATR, STOPS, TARGETS_R, FILTERS
    ):
        cid = (
            f"orb{anchor:02d}_buf{str(buffer_atr).replace('.', 'p')}_"
            f"{stop}_{str(target).replace('.', 'p')}R_{filt}"
        )
        configs.append({
            "config_id": cid, "anchor_hour_utc": anchor,
            "buffer_atr": buffer_atr, "stop": stop,
            "target_r": target, "filter": filt,
            "signals": signal_cache[(anchor, buffer_atr)],
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

    # Detailed train/validation trade records for the top in-sample row and
    # the best validation-only row are diagnostics, not OOS selection.
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
        config = next(c for c in configs if c["config_id"] == selected.config_id)
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
        "execution": "15m close breakout after a completed one-hour UTC opening range; next-open entry; 8h max hold; one position/config; SL first; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train screen then validation screen; OOS once only for the single validation-selected candidate",
        "opening_range": "four completed 15m bars from each UTC anchor 00:00, 07:00, 13:00, 19:00; first close outside range in the following UTC block",
        "filters": "optional EMA50 on completed 1H bars only",
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
