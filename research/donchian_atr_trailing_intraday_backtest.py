"""Intraday BTCUSD Donchian breakout with causal ATR chandelier trailing exits.

Research-only: 15m signals, next-open entries, 8h maximum hold.
A trailing stop calculated from a completed bar becomes active on the next bar.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("donchian_atr_trailing_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_BPS = (6, 12, 20)
CHANNELS = (20, 55)
INITIAL_ATR = (1.5, 2.0)
TRAIL_ATR = (2.0, 3.0)
TARGETS_R = (None, 2.0, 3.0, 4.0)
HTF_FILTERS = ("none", "ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MAX_SHORTLIST = 25


def rma(series, length):
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < length or not np.isfinite(values[:length]).all():
        return pd.Series(out, index=series.index)
    out[length - 1] = float(np.mean(values[:length]))
    for i in range(length, len(values)):
        if np.isfinite(values[i]):
            out[i] = (out[i - 1] * (length - 1) + values[i]) / length
        else:
            out[i] = np.nan
    return pd.Series(out, index=series.index)


def prepare_data(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d[(d.high >= d[["open", "close", "low"]].max(axis=1)) &
          (d.low <= d[["open", "close", "high"]].min(axis=1))]
    d["segment"] = d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    d["atr14"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        idx = g.index
        prev_close = g.close.shift(1)
        tr = pd.concat(
            [g.high - g.low, (g.high - prev_close).abs(), (g.low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        d.loc[idx, "atr14"] = rma(tr, 14).to_numpy()
        for length in CHANNELS:
            d.loc[idx, f"dc{length}_high"] = g.high.shift(1).rolling(
                length, min_periods=length
            ).max().to_numpy()
            d.loc[idx, f"dc{length}_low"] = g.low.shift(1).rolling(
                length, min_periods=length
            ).min().to_numpy()

    # Build only complete hourly candles containing four contiguous 15m bars
    # from the same 15m data segment. Right-edge timestamps prevent lookahead.
    hourly = d[["open", "high", "low", "close"]].resample(
        "1h", label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample("1h", label="right", closed="left").count()
    segment_counts = d.segment.resample("1h", label="right", closed="left").nunique()
    hourly = hourly.loc[counts.eq(4) & segment_counts.eq(1)].dropna()
    hseg = hourly.index.to_series().diff().ne(pd.Timedelta("1h")).cumsum()
    hourly["ema50"] = hourly.groupby(hseg).close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    hourly["ema200"] = hourly.groupby(hseg).close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    d["h_close"] = hourly.close.reindex(d.index, method="ffill")
    d["h_ema50"] = hourly.ema50.reindex(d.index, method="ffill")
    d["h_ema200"] = hourly.ema200.reindex(d.index, method="ffill")
    bull = (d.h_close > d.h_ema50) & (d.h_ema50 > d.h_ema200)
    bear = (d.h_close < d.h_ema50) & (d.h_ema50 < d.h_ema200)
    d["trend_regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )
    return d


def build_signals(d, channel):
    hi = d[f"dc{channel}_high"].to_numpy(float)
    lo = d[f"dc{channel}_low"].to_numpy(float)
    close = d.close.to_numpy(float)
    atr = d.atr14.to_numpy(float)
    seg = d.segment.to_numpy()
    signals = []
    for i in range(len(d) - 1):
        if seg[i] != seg[i + 1]:
            continue
        if not np.isfinite([hi[i], lo[i], atr[i]]).all() or atr[i] <= 0:
            continue
        side = "long" if close[i] > hi[i] else (
            "short" if close[i] < lo[i] else None
        )
        if side:
            signals.append({
                "signal_i": i,
                "entry_i": i + 1,
                "side": side,
                "atr_signal": float(atr[i]),
            })
    return signals


def metrics(g, cost_bps):
    if g.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": None,
            "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "positive_month_fraction": 0.0,
        }
    x = g.sort_values("entry_time")
    r = x[f"net_R_{cost_bps}bp"].astype(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = r.cumsum().to_numpy()
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]
    streak = maximum = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        maximum = max(maximum, streak)
    monthly = x.assign(month=x.entry_time.dt.strftime("%Y-%m")).groupby("month")[
        f"net_R_{cost_bps}bp"
    ].sum()
    return {
        "trades": int(len(x)),
        "win_rate_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 2),
        "max_losing_streak": int(maximum),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3)
        if len(monthly) else 0.0,
        "TP": int((x.outcome == "TP").sum()),
        "SL": int((x.outcome == "SL").sum()),
        "TIME": int((x.outcome == "TIME").sum()),
    }


def simulate(d, signals, cfg, start_i, end_i):
    opens = d.open.to_numpy(float)
    highs = d.high.to_numpy(float)
    lows = d.low.to_numpy(float)
    closes = d.close.to_numpy(float)
    atr = d.atr14.to_numpy(float)
    seg = d.segment.to_numpy()
    hclose = d.h_close.to_numpy(float)
    hema50 = d.h_ema50.to_numpy(float)
    hema200 = d.h_ema200.to_numpy(float)
    regimes = d.trend_regime.to_numpy()
    rows = []
    last_exit_i = start_i - 1

    for sig in signals:
        si, ei, side = sig["signal_i"], sig["entry_i"], sig["side"]
        if si < start_i or ei >= end_i or ei <= last_exit_i:
            continue
        if cfg["direction"] == "long_only" and side != "long":
            continue
        if cfg["direction"] == "short_only" and side != "short":
            continue
        entry_time = d.index[ei]
        if cfg["session"] == "07-19" and not (7 <= entry_time.hour < 19):
            continue
        if cfg["htf_filter"] == "ema50_200":
            if not np.isfinite([hclose[si], hema50[si], hema200[si]]).all():
                continue
            aligned = (
                side == "long" and hclose[si] > hema50[si] > hema200[si]
            ) or (
                side == "short" and hclose[si] < hema50[si] < hema200[si]
            )
            if not aligned:
                continue

        # Require a full 8h evaluation window inside this sample and one
        # uninterrupted data segment. This avoids sample-boundary and gap leakage.
        stop_window = ei + MAX_HOLD_BARS
        if stop_window > end_i or stop_window > len(d):
            continue
        if not np.all(seg[ei:stop_window] == seg[ei]):
            continue
        entry = float(opens[ei])
        initial_risk = float(cfg["initial_atr"] * sig["atr_signal"])
        stop = entry - initial_risk if side == "long" else entry + initial_risk
        risk = entry - stop if side == "long" else stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target_r = cfg["target_r"]
        target = (
            entry + target_r * risk if side == "long"
            else entry - target_r * risk
        ) if target_r is not None else np.nan

        active_stop = stop
        high_water = entry
        low_water = entry
        outcome = "TIME"
        exit_price = float(closes[ei + MAX_HOLD_BARS - 1])
        exit_i = ei + MAX_HOLD_BARS - 1

        for j in range(ei, ei + MAX_HOLD_BARS):
            op, bh, bl = float(opens[j]), float(highs[j]), float(lows[j])
            sl_hit = bl <= active_stop if side == "long" else bh >= active_stop
            tp_hit = (
                bh >= target if side == "long" else bl <= target
            ) if target_r is not None else False

            # Conservative OHLC ambiguity: stop is checked before target.
            if sl_hit:
                outcome = "SL"
                exit_price = min(active_stop, op) if side == "long" else max(active_stop, op)
                exit_i = j
                break
            if tp_hit:
                outcome = "TP"
                exit_price = target
                exit_i = j
                break

            # Update the chandelier only after this candle closes; the new
            # stop is therefore active from the next candle, never retroactively.
            high_water = max(high_water, bh)
            low_water = min(low_water, bl)
            if np.isfinite(atr[j]) and atr[j] > 0:
                if side == "long":
                    candidate = high_water - cfg["trail_atr"] * float(atr[j])
                    active_stop = max(active_stop, candidate)
                else:
                    candidate = low_water + cfg["trail_atr"] * float(atr[j])
                    active_stop = min(active_stop, candidate)

        gross_r = (
            (exit_price - entry) / risk if side == "long"
            else (entry - exit_price) / risk
        )
        row = {
            "config_id": cfg["config_id"],
            "channel": cfg["channel"],
            "initial_atr": cfg["initial_atr"],
            "trail_atr": cfg["trail_atr"],
            "target_r": "trail_only" if target_r is None else target_r,
            "htf_filter": cfg["htf_filter"],
            "direction": cfg["direction"],
            "session": cfg["session"],
            "sample": cfg["sample"],
            "side": side,
            "signal_time": d.index[si],
            "entry_time": entry_time,
            "exit_time": d.index[exit_i],
            "entry": entry,
            "initial_stop": stop,
            "final_active_stop": active_stop,
            "target": target,
            "exit": exit_price,
            "outcome": outcome,
            "gross_R": gross_r,
            "trend_regime": regimes[ei],
        }
        for bps in COST_BPS:
            cost_rate = bps / 10000.0
            cost_r = cost_rate * entry / risk
            row[f"cost_R_{bps}bp"] = cost_r
            row[f"net_R_{bps}bp"] = gross_r - cost_r
        rows.append(row)
        last_exit_i = exit_i
    return rows


def main():
    raw = fetch("15m").sort_index()
    d = prepare_data(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m history: {len(d)} rows")
    diffs = d.index.to_series().diff().dropna()
    gaps = int((diffs != BAR).sum())
    if gaps:
        print(f"DATA QUALITY WARNING: {gaps} non-15m intervals; simulations are segmented and skip gap-crossing trades.")

    n = len(d)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    samples = (
        ("train", 0, train_end),
        ("validation", train_end, validation_end),
        ("oos", validation_end, n),
    )
    dataset_sha = hashlib.sha256(d.to_csv().encode()).hexdigest()
    signals_by_channel = {ch: build_signals(d, ch) for ch in CHANNELS}
    configs = []
    for values in itertools.product(
        CHANNELS, INITIAL_ATR, TRAIL_ATR, TARGETS_R,
        HTF_FILTERS, DIRECTIONS, SESSIONS
    ):
        channel, initial_atr, trail_atr, target_r, htf_filter, direction, session = values
        cfg_id = (
            f"dc{channel}_init{initial_atr}_trail{trail_atr}_"
            f"{'trail_only' if target_r is None else str(target_r)+'R'}_"
            f"{htf_filter}_{direction}_{session}"
        )
        configs.append({
            "config_id": cfg_id, "channel": channel,
            "initial_atr": initial_atr, "trail_atr": trail_atr,
            "target_r": target_r, "htf_filter": htf_filter,
            "direction": direction, "session": session,
        })

    all_trades = []
    summaries = []
    for cfg in configs:
        for sample, start_i, end_i in samples:
            run_cfg = cfg | {"sample": sample}
            rows = simulate(d, signals_by_channel[cfg["channel"]], run_cfg, start_i, end_i)
            if rows:
                all_trades.extend(rows)
            g = pd.DataFrame(rows)
            for bps in COST_BPS:
                summaries.append(
                    run_cfg | {"cost_bps": bps} | metrics(g, bps)
                )

    trades = pd.DataFrame(all_trades)
    if trades.empty:
        raise RuntimeError("No Donchian ATR-trailing trades generated.")
    trades.to_csv(OUT / "trades.csv", index=False)
    summary = pd.DataFrame(summaries)
    for sample in ("train", "validation", "oos"):
        summary[summary["sample"] == sample].to_csv(
            OUT / f"{sample}_summary.csv", index=False
        )

    base = summary[summary.cost_bps.eq(12)]
    train = base[base["sample"].eq("train")].copy()
    validation = base[base["sample"].eq("validation")].copy()
    eligible = train[
        (train.trades >= MIN_TRAIN_TRADES) & (train.net_R > 0) &
        (train.profit_factor >= 1.05) & (train.max_drawdown_R >= -25.0)
    ].copy()
    if not eligible.empty:
        eligible["selection_score"] = eligible.net_R / (
            eligible.max_drawdown_R.abs() + 1.0
        )
        shortlist = eligible.sort_values(
            ["selection_score", "net_R"], ascending=False
        ).head(MAX_SHORTLIST)
    else:
        shortlist = eligible.copy()

    joined = shortlist.merge(
        validation, on="config_id", suffixes=("_train", "_validation")
    ) if not shortlist.empty else pd.DataFrame()
    if not joined.empty:
        passes = joined[
            (joined.trades_validation >= MIN_VALIDATION_TRADES) &
            (joined.net_R_validation > 0) &
            (joined.profit_factor_validation >= 1.05) &
            (joined.max_drawdown_R_validation >= -15.0) &
            (joined.positive_month_fraction_validation >= 0.50)
        ].copy()
    else:
        passes = pd.DataFrame()

    selected = None
    if not passes.empty:
        selected = passes.sort_values(
            ["selection_score", "net_R_train"], ascending=False
        ).iloc[0]["config_id"]
    oos_evaluated = selected is not None
    oos_selected = (
        base[(base["sample"].eq("oos")) & base.config_id.eq(selected)]
        if oos_evaluated else pd.DataFrame()
    )

    # Month and trend-regime diagnostics at the base 12bp cost.
    month_rows = []
    regime_rows = []
    for cfg_id, g in trades.groupby("config_id", sort=False):
        for sample in ("train", "validation", "oos"):
            part = g[g["sample"].eq(sample)].copy()
            if part.empty:
                continue
            part["month"] = part.entry_time.dt.strftime("%Y-%m")
            for month, mg in part.groupby("month"):
                m = metrics(mg, 12)
                month_rows.append({"config_id": cfg_id, "sample": sample, "month": month} | m)
            for regime, rg in part.groupby("trend_regime"):
                m = metrics(rg, 12)
                regime_rows.append({"config_id": cfg_id, "sample": sample, "trend_regime": regime} | m)
    pd.DataFrame(month_rows).to_csv(OUT / "monthly_summary.csv", index=False)
    pd.DataFrame(regime_rows).to_csv(OUT / "regime_summary.csv", index=False)
    if not joined.empty:
        joined.to_csv(OUT / "shortlist_validation.csv", index=False)
    if not passes.empty:
        passes.to_csv(OUT / "validation_passes.csv", index=False)
    if oos_evaluated:
        oos_selected.to_csv(OUT / "selected_oos_summary.csv", index=False)
        trades[(trades.config_id.eq(selected)) & trades["sample"].eq("oos")].to_csv(
            OUT / "selected_oos_trades.csv", index=False
        )
        trades[(trades.config_id.eq(selected)) & trades["sample"].eq("oos")].assign(
            month=lambda x: x.entry_time.dt.strftime("%Y-%m")
        ).to_csv(OUT / "selected_oos_monthly_trades.csv", index=False)
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the pre-registered training and validation filters; OOS was not evaluated.\n"
        )

    meta = {
        "symbol": "BTCUSD", "timeframe": "15m", "rows": len(d),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps": gaps, "dataset_sha256": dataset_sha,
        "train_end_utc": str(d.index[train_end - 1]),
        "validation_end_utc": str(d.index[validation_end - 1]),
        "oos_start_utc": str(d.index[validation_end]),
        "matrix_configurations": len(configs),
        "train_eligible": len(eligible), "shortlisted": len(shortlist),
        "validation_pass": len(passes), "selected_oos_config": selected,
        "oos_evaluated": oos_evaluated,
        "cost_sensitivity_bps": list(COST_BPS),
        "cost_assumption": "6/12/20bp round-trip sensitivity; no funding or separate spread/slippage",
        "execution": "prior shifted Donchian 20/55 close breakout; next 15m open; initial 1.5/2 ATR stop; 2/3 ATR chandelier updated at completed-bar close and active next bar; optional 2R/3R/4R target or trail-only; 8h max hold; stop-first same-bar ambiguity; adverse gap-through stop fill",
        "split": "chronological 70/15/15; training screen then validation screen; OOS once only for one selected validation-passing candidate",
        "htf_context": "optional completed 1h EMA50/EMA200 alignment; only complete 4x15m hours; right-edge timestamp; bull/bear/mixed trend regime",
        "selection": {
            "train": ">=40 trades, net_R>0, PF>=1.05, max DD>=-25R",
            "validation": ">=20 trades, net_R>0, PF>=1.05, max DD>=-15R, >=50% positive active months",
            "shortlist": f"top {MAX_SHORTLIST} by train net_R/(abs(max_drawdown_R)+1)"
        },
        "limitations": "12bp is the primary selection cost but unverified; 6/20bp are sensitivities; no funding or separate spread/slippage; fixed 07-19 UTC session proxy; OHLC intrabar ambiguity resolves stop first; trailing stop uses completed bar data and applies next bar",
    }
    (OUT / "methodology.json").write_text(json.dumps(meta, indent=2))
    print("DATA/METHOD", json.dumps(meta, indent=2))
    print("\nTOP TRAIN (12bp, nonzero trades)")
    print(train[train.trades.gt(0)].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print("\nTOP VALIDATION (12bp, nonzero trades)")
    print(validation[validation.trades.gt(0)].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)} SHORTLIST={len(shortlist)} VALIDATION PASS={len(passes)}")
    if oos_evaluated:
        print("\nSELECTED OOS (12bp)")
        print(oos_selected.to_string(index=False))
    else:
        print("OOS NOT EVALUATED: no candidate passed the pre-registered train/validation gates.")


if __name__ == "__main__":
    main()
