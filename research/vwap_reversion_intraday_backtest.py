"""Intraday BTCUSD UTC-anchored VWAP deviation reversion research.

Uses exchange-reported candle volume as a weighting proxy; this is not a
market-wide consolidated VWAP. Bands for each signal candle are calculated
from completed prior 15m bars only. Entry is next 15m open; max hold is 8h.
Train/validation select one candidate before OOS is evaluated once.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("vwap_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
COST_RATE = 0.0012
BANDS = (1.0, 1.5, 2.0)
CONFIRMATIONS = ("reclaim", "engulfing_reclaim")
STOPS = ("signal_extreme", "atr1", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h_trend")
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
    if "volume" not in d.columns:
        raise RuntimeError("Delta candle response has no volume field; VWAP test cannot run.")
    d["volume"] = pd.to_numeric(d.volume, errors="coerce").fillna(0.0)
    if (d.volume < 0).any() or d.volume.sum() <= 0:
        raise RuntimeError("Invalid or empty candle volume series.")

    previous = d.close.shift(1)
    tr = pd.concat(
        [d.high - d.low, (d.high - previous).abs(), (d.low - previous).abs()],
        axis=1,
    ).max(axis=1)
    d["atr15"] = rma(tr, 14)

    typical = (d.high + d.low + d.close) / 3.0
    day = d.index.normalize()
    cum_vol = d.volume.groupby(day).cumsum()
    cum_pv = (typical * d.volume).groupby(day).cumsum()
    cum_p2v = (typical.pow(2) * d.volume).groupby(day).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    variance = (cum_p2v / cum_vol.replace(0, np.nan) - vwap.pow(2)).clip(lower=0)
    sd = np.sqrt(variance)
    same_day = day == day.to_series().shift(1).array
    # Shift all reference statistics one candle: signal candle compares with
    # bands that were fully known before it opened.
    d["vwap_ref"] = vwap.shift(1).where(same_day)
    d["vwap_sd_ref"] = sd.shift(1).where(same_day)

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    h_count = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[h_count.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(span=50, adjust=False, min_periods=50).mean()
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    return d, hourly


def build_signals(d, band_mult, confirmation):
    close = d.close.to_numpy(dtype=float)
    open_ = d.open.to_numpy(dtype=float)
    high = d.high.to_numpy(dtype=float)
    low = d.low.to_numpy(dtype=float)
    atr = d.atr15.to_numpy(dtype=float)
    vwap = d.vwap_ref.to_numpy(dtype=float)
    sd = d.vwap_sd_ref.to_numpy(dtype=float)
    lower = vwap - band_mult * sd
    upper = vwap + band_mult * sd
    signals = []

    for i in range(1, len(d) - 1):
        if not (np.isfinite(lower[i-1]) and np.isfinite(upper[i-1])
                and np.isfinite(lower[i]) and np.isfinite(upper[i])
                and np.isfinite(vwap[i]) and np.isfinite(atr[i]) and atr[i] > 0):
            continue

        side = None
        if close[i-1] < lower[i-1] and close[i] > lower[i] and close[i] < vwap[i]:
            side = "long"
            if confirmation == "engulfing_reclaim":
                bullish_engulf = (
                    close[i] > open_[i] and open_[i] <= close[i-1]
                    and close[i] >= open_[i-1]
                )
                if not bullish_engulf:
                    side = None
        elif close[i-1] > upper[i-1] and close[i] < upper[i] and close[i] > vwap[i]:
            side = "short"
            if confirmation == "engulfing_reclaim":
                bearish_engulf = (
                    close[i] < open_[i] and open_[i] >= close[i-1]
                    and close[i] <= open_[i-1]
                )
                if not bearish_engulf:
                    side = None
        if side:
            signals.append({
                "signal_i": i, "entry_i": i + 1, "side": side,
                "extreme": float(low[i] if side == "long" else high[i]),
                "atr_signal": float(atr[i]), "band_mult": band_mult,
            })
    return signals


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
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) else None,
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
        entry_i, signal_i = sig["entry_i"], sig["signal_i"]
        if entry_i < start_i or entry_i >= end_i or entry_i <= last_exit:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if not in_session(idx[entry_i], config["session"]):
            continue
        side = sig["side"]
        if config["filter"] == "ema50_1h_trend":
            e = ema[signal_i]
            if not np.isfinite(e) or (side == "long" and closes[signal_i] <= e) or (side == "short" and closes[signal_i] >= e):
                continue
        if gap_mask[signal_i : entry_i + MAX_HOLD_BARS].any():
            continue

        entry = float(opens[entry_i])
        if config["stop"] == "signal_extreme":
            pad = 0.1 * sig["atr_signal"]
            stop = sig["extreme"] - pad if side == "long" else sig["extreme"] + pad
        else:
            mult = 1.0 if config["stop"] == "atr1" else 1.5
            distance = mult * sig["atr_signal"]
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
                exit_price = target
                exit_i = j
                break
        gross_r = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        cost_r = entry * COST_RATE / risk
        rows.append({
            "entry_time": idx[entry_i], "exit_time": idx[exit_i], "side": side,
            "entry": entry, "stop": stop, "target": target, "exit": exit_price,
            "outcome": outcome, "gross_R": gross_r, "estimated_cost_R": cost_r,
            "net_R": gross_r - cost_r,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def main():
    raw = fetch("15m")
    d, hourly = prepare_data(raw)
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
        "hourly_complete_bars": int(len(hourly)),
        "volume_zero_bars": int((d.volume <= 0).sum()),
        "volume_sum": float(d.volume.sum()),
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    configs = []
    for band, confirmation in itertools.product(BANDS, CONFIRMATIONS):
        signal_cache[(band, confirmation)] = build_signals(d, band, confirmation)
    for band, confirmation, stop, target, filt, session in itertools.product(
        BANDS, CONFIRMATIONS, STOPS, TARGETS_R, FILTERS, SESSIONS
    ):
        cid = f"band{str(band).replace('.', 'p')}_{confirmation}_{stop}_{str(target).replace('.', 'p')}R_{filt}_{session}"
        configs.append({
            "config_id": cid, "band_mult": band, "confirmation": confirmation,
            "stop": stop, "target_r": target, "filter": filt, "session": session,
            "signals": signal_cache[(band, confirmation)],
        })

    train_rows, validation_rows = [], []
    for c in configs:
        base = {k: v for k, v in c.items() if k != "signals"}
        for sample in ("train", "validation"):
            t = simulate(d, c["signals"], c, *segments[sample], gap_mask)
            row = base | {"sample": sample} | metrics(t)
            (train_rows if sample == "train" else validation_rows).append(row)
    train_df, validation_df = pd.DataFrame(train_rows), pd.DataFrame(validation_rows)
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
        shortlist, eligible_validation = pd.DataFrame(), pd.DataFrame()

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
            oos.assign(month=oos.entry_time.dt.strftime("%Y-%m")).groupby("month").agg(
                trades=("net_R", "size"), net_R=("net_R", "sum"),
                profitable_pct=("net_R", lambda x: float((x > 0).mean() * 100))
            ).reset_index().to_csv(OUT / "oos_monthly.csv", index=False)
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
        "volume_note": "Delta candle volume is an exchange-specific contract-volume proxy, not consolidated market-wide volume",
        "execution": "15m next-open entries; 8h max hold; SL first; adverse gap-through stop fills; one position/configuration",
        "split": "chronological 70/15/15; OOS only for the single validation-selected configuration",
        "vwap": "UTC-day anchored cumulative VWAP and weighted standard deviation; signal bands lagged one full 15m bar",
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
