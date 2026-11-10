"""Intraday BTCUSD market-structure break/retest research.

15m execution; confirmed 1H pivots are used only after their right-hand bars
close. Entries are next-open after a breakout close or a later retest/reclaim.
Maximum holding period is 8 hours. Candidate selection uses train/validation
only; OOS is simulated once for the single validation-selected configuration.
Experimental research only.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("mss_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
HOUR = pd.Timedelta("1h")
MAX_HOLD_BARS = 32
MAX_RETEST_BARS = 8
COST_RATE = 0.0012  # assumed 12bp round trip; fee tier not verified
PIVOT_STRENGTHS = (3, 5)
ENTRY_MODES = ("breakout", "retest")
STOP_MODES = ("breakout_extreme", "atr1", "atr1p5")
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
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    hourly["ema50"] = hourly.close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    # Right-labelled hourly EMA is visible only from the completed hour onward.
    d["ema50_1h"] = hourly.ema50.reindex(d.index, method="ffill")
    return d, hourly


def confirmed_pivot_events(d, hourly, strength):
    """Map each strict 1H pivot to its first causally available 15m bar."""
    high_events, low_events = {}, {}
    highs = hourly.high.to_numpy(dtype=float)
    lows = hourly.low.to_numpy(dtype=float)
    times = hourly.index
    left = right = strength

    for i in range(left, len(hourly) - right):
        window = times[i - left : i + right + 1]
        if len(window) != left + right + 1:
            continue
        if (window.to_series().diff().dropna() != HOUR).any():
            continue
        is_high = (
            highs[i] > np.max(highs[i - left : i])
            and highs[i] > np.max(highs[i + 1 : i + right + 1])
        )
        is_low = (
            lows[i] < np.min(lows[i - left : i])
            and lows[i] < np.min(lows[i + 1 : i + right + 1])
        )
        confirm_time = times[i + right]
        pos = int(d.index.searchsorted(confirm_time, side="left"))
        if pos >= len(d):
            continue
        if is_high:
            high_events.setdefault(pos, []).append((float(highs[i]), confirm_time))
        if is_low:
            low_events.setdefault(pos, []).append((float(lows[i]), confirm_time))
    return high_events, low_events


def build_break_signals(d, hourly, strength, entry_mode):
    """Build causal BOS and (optionally) first retest/reclaim signals."""
    high_events, low_events = confirmed_pivot_events(d, hourly, strength)
    close = d.close.to_numpy(dtype=float)
    high = d.high.to_numpy(dtype=float)
    low = d.low.to_numpy(dtype=float)
    atr = d.atr15.to_numpy(dtype=float)
    active_high = None
    active_low = None
    breakouts = []

    for i in range(1, len(d) - 1):
        if i in high_events:
            active_high = high_events[i][-1]
        if i in low_events:
            active_low = low_events[i][-1]

        if active_high is not None and close[i] > active_high[0]:
            level, level_time = active_high
            if close[i - 1] <= level and np.isfinite(atr[i]) and atr[i] > 0:
                breakouts.append({
                    "breakout_i": i, "signal_i": i, "entry_i": i + 1,
                    "side": "long", "level": level, "level_time": level_time,
                    "breakout_extreme": float(low[i]), "atr_signal": float(atr[i]),
                })
            active_high = None

        if active_low is not None and close[i] < active_low[0]:
            level, level_time = active_low
            if close[i - 1] >= level and np.isfinite(atr[i]) and atr[i] > 0:
                breakouts.append({
                    "breakout_i": i, "signal_i": i, "entry_i": i + 1,
                    "side": "short", "level": level, "level_time": level_time,
                    "breakout_extreme": float(high[i]), "atr_signal": float(atr[i]),
                })
            active_low = None

    if entry_mode == "breakout":
        return sorted(breakouts, key=lambda x: x["entry_i"])

    signals = []
    for b in breakouts:
        i = b["breakout_i"]
        side = b["side"]
        level = b["level"]
        found = None
        # Retest must occur within the next eight completed 15m candles.
        for j in range(i + 1, min(i + MAX_RETEST_BARS + 1, len(d) - 1)):
            if not np.isfinite(atr[j]) or atr[j] <= 0:
                continue
            if side == "long":
                if close[j] < level:  # decisive close back below broken resistance
                    break
                if low[j] <= level and close[j] > level:
                    found = j
                    break
            else:
                if close[j] > level:  # decisive close back above broken support
                    break
                if high[j] >= level and close[j] < level:
                    found = j
                    break
        if found is not None:
            signals.append({
                **b,
                "signal_i": found,
                "entry_i": found + 1,
                "atr_signal": float(atr[found]),
            })
    return sorted(signals, key=lambda x: x["entry_i"])


def in_session(ts, session):
    if session == "all":
        return True
    hour = ts.hour
    bounds = {
        "00-07": (0, 7), "07-13": (7, 13),
        "13-19": (13, 19), "19-24": (19, 24),
    }
    lo, hi = bounds[session]
    return lo <= hour < hi


def streak_metrics(values):
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
            "positive_month_fraction": 0.0,
        }
    g = trades.sort_values("entry_time")
    r = g.net_R.astype(float)
    wins = r[r > 0]
    losses = r[r < 0]
    equity = r.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    dd = equity - peak
    monthly = g.assign(month=g.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(g)),
        "profitable_pct": round(float((r > 0).mean() * 100), 2),
        "tp_rate_pct": round(float((g.outcome == "TP").mean() * 100), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) > 0 else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 2),
        "max_losing_streak": int(streak_metrics(r.to_numpy())),
        "TP": int((g.outcome == "TP").sum()),
        "SL": int((g.outcome == "SL").sum()),
        "TIME": int((g.outcome == "TIME").sum()),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3)
        if len(monthly) else 0.0,
    }


def simulate_config(d, signals, config, start_i, end_i, gap_mask):
    """One-position-at-a-time simulation inside one chronological sample."""
    opens = d.open.to_numpy(dtype=float)
    highs = d.high.to_numpy(dtype=float)
    lows = d.low.to_numpy(dtype=float)
    closes = d.close.to_numpy(dtype=float)
    ema = d.ema50_1h.to_numpy(dtype=float)
    idx = d.index
    trades = []
    last_exit_i = -1

    for sig in signals:
        entry_i = sig["entry_i"]
        signal_i = sig["signal_i"]
        if entry_i < start_i or entry_i >= end_i:
            continue
        if entry_i <= last_exit_i:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if not in_session(idx[entry_i], config["session"]):
            continue
        side = sig["side"]
        if config["filter"] == "ema50_1h":
            e = ema[signal_i]
            if not np.isfinite(e):
                continue
            if (side == "long" and closes[signal_i] <= e) or (
                side == "short" and closes[signal_i] >= e
            ):
                continue

        # Any missing 15m bar inside the holding window invalidates the test.
        if gap_mask[entry_i + 1 : entry_i + MAX_HOLD_BARS].any():
            continue

        entry = float(opens[entry_i])
        if config["stop"] == "breakout_extreme":
            stop = sig["breakout_extreme"]
        else:
            mult = 1.0 if config["stop"] == "atr1" else 1.5
            distance = mult * sig["atr_signal"]
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
        exit_price = float(closes[entry_i + MAX_HOLD_BARS - 1])
        exit_i = entry_i + MAX_HOLD_BARS - 1
        for j in range(entry_i, entry_i + MAX_HOLD_BARS):
            stop_hit = lows[j] <= stop if side == "long" else highs[j] >= stop
            target_hit = highs[j] >= target if side == "long" else lows[j] <= target
            if stop_hit:  # conservative same-candle ambiguity: stop first
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
        trades.append({
            "entry_time": idx[entry_i], "exit_time": idx[exit_i],
            "side": side, "entry": entry, "stop": stop, "target": target,
            "exit": exit_price, "outcome": outcome,
            "gross_R": gross_r, "estimated_cost_R": cost_r,
            "net_R": gross_r - cost_r,
        })
        last_exit_i = exit_i
    return pd.DataFrame(trades)


def config_id(pivot, entry, stop, target, filt, session):
    target_text = str(target).replace(".", "p")
    return f"p{pivot}_{entry}_{stop}_{target_text}R_{filt}_{session}"


def main():
    raw = fetch("15m")
    d, hourly = prepare_data(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m history: {len(d)} rows")

    n = len(d)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    split_train_time = d.index[train_end]
    split_validation_time = d.index[validation_end]
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
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "rows": int(len(d)),
        "start_utc": str(d.index.min()),
        "end_utc": str(d.index.max()),
        "gaps": int((diffs.dropna() != BAR).sum()),
        "largest_gap_minutes": float(diffs.dropna().max().total_seconds() / 60),
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "hourly_complete_bars": int(len(hourly)),
        "train_end_utc": str(split_train_time),
        "validation_end_utc": str(split_validation_time),
        "oos_start_utc": str(split_validation_time),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    signal_cache = {}
    configs = []
    for pivot, entry_mode, stop, target, filt, session in itertools.product(
        PIVOT_STRENGTHS, ENTRY_MODES, STOP_MODES, TARGETS_R, FILTERS, SESSIONS
    ):
        key = (pivot, entry_mode)
        if key not in signal_cache:
            signal_cache[key] = build_break_signals(d, hourly, pivot, entry_mode)
        configs.append({
            "config_id": config_id(pivot, entry_mode, stop, target, filt, session),
            "pivot_strength": pivot, "entry_mode": entry_mode,
            "stop": stop, "target_r": target, "filter": filt, "session": session,
            "signals": signal_cache[key],
        })

    train_rows = []
    validation_rows = []
    for c in configs:
        row = {k: v for k, v in c.items() if k != "signals"}
        for sample in ("train", "validation"):
            trades = simulate_config(d, c["signals"], c, *segments[sample], gap_mask)
            summary = metrics(trades)
            result = row | {"sample": sample} | summary
            if sample == "train":
                train_rows.append(result)
            else:
                validation_rows.append(result)

    train_df = pd.DataFrame(train_rows)
    validation_df = pd.DataFrame(validation_rows)
    train_df.to_csv(OUT / "train_summary.csv", index=False)
    validation_df.to_csv(OUT / "validation_summary.csv", index=False)

    # Candidate funnel is fixed before OOS: train screen, then validation screen.
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
        train_candidates = eligible_train.sort_values(
            ["train_quality", "trades"], ascending=[False, False]
        ).head(MAX_TRAIN_CANDIDATES)
        eligible_validation = validation_df[
            validation_df.config_id.isin(train_candidates.config_id)
            & (validation_df.trades >= MIN_VALIDATION_TRADES)
            & (validation_df.net_R > 0)
            & (validation_df.profit_factor >= 1.05)
            & (validation_df.max_drawdown_R >= -15.0)
            & (validation_df.positive_month_fraction >= 0.50)
        ].copy()
    else:
        train_candidates = pd.DataFrame()
        eligible_validation = pd.DataFrame()

    selected = None
    oos_trades = pd.DataFrame()
    oos_summary = {}
    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = (
            eligible_validation.net_R
            / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        )
        chosen = eligible_validation.sort_values(
            ["validation_quality", "trades"], ascending=[False, False]
        ).iloc[0]
        selected = next(c for c in configs if c["config_id"] == chosen.config_id)
        oos_trades = simulate_config(
            d, selected["signals"], selected, *segments["oos"], gap_mask
        )
        oos_summary = (
            {k: v for k, v in selected.items() if k != "signals"}
            | {"sample": "oos"}
            | metrics(oos_trades)
        )
        oos_trades.to_csv(OUT / "chosen_oos_trades.csv", index=False)

        if not oos_trades.empty:
            monthly = (
                oos_trades.assign(month=oos_trades.entry_time.dt.strftime("%Y-%m"))
                .groupby("month", as_index=False)
                .agg(trades=("net_R", "size"), net_R=("net_R", "sum"),
                     profitable_pct=("net_R", lambda x: (x > 0).mean() * 100))
            )
            monthly.to_csv(OUT / "chosen_oos_monthly.csv", index=False)
            bucket_map = {
                "00-07": lambda h: 0 <= h < 7,
                "07-13": lambda h: 7 <= h < 13,
                "13-19": lambda h: 13 <= h < 19,
                "19-24": lambda h: 19 <= h < 24,
            }
            oos_trades = oos_trades.copy()
            oos_trades["utc_bucket"] = oos_trades.entry_time.dt.hour.map(
                lambda h: next(k for k, fn in bucket_map.items() if fn(h))
            )
            bucket_rows = []
            for bucket, group in oos_trades.groupby("utc_bucket"):
                bucket_rows.append({"utc_bucket": bucket} | metrics(group))
            pd.DataFrame(bucket_rows).to_csv(OUT / "chosen_oos_utc_buckets.csv", index=False)
        else:
            pd.DataFrame(columns=["month", "trades", "net_R", "profitable_pct"]).to_csv(
                OUT / "chosen_oos_monthly.csv", index=False
            )
            pd.DataFrame(columns=["utc_bucket", "trades", "net_R"]).to_csv(
                OUT / "chosen_oos_utc_buckets.csv", index=False
            )
    else:
        pd.DataFrame().to_csv(OUT / "chosen_oos_trades.csv", index=False)
        pd.DataFrame(columns=["month", "trades", "net_R", "profitable_pct"]).to_csv(
            OUT / "chosen_oos_monthly.csv", index=False
        )
        pd.DataFrame(columns=["utc_bucket", "trades", "net_R"]).to_csv(
            OUT / "chosen_oos_utc_buckets.csv", index=False
        )

    (OUT / "selection.json").write_text(json.dumps({
        "configuration_count": len(configs),
        "train_eligible_count": int(len(eligible_train)),
        "train_shortlist_count": int(len(train_candidates)),
        "validation_pass_count": int(len(eligible_validation)),
        "selected_config": (
            {k: v for k, v in selected.items() if k != "signals"}
            if selected else None
        ),
        "selected_oos_summary": oos_summary if selected else None,
        "selection_rule": (
            "Train: >=40 trades, net_R>0, PF>=1.05, max DD>=-25R; shortlist top 25 "
            "by net_R/abs(maxDD). Validation: shortlisted only, >=20 trades, net_R>0, "
            "PF>=1.05, max DD>=-15R, positive in >=50% of active months; select highest "
            "validation net_R/abs(maxDD). OOS evaluated once for the selected config only."
        ),
    }, indent=2, default=str))

    methodology = {
        "hypothesis": "15m close beyond a causally confirmed 1H swing level may continue; retest/reclaim may improve entry quality.",
        "pivot": "Strict 1H pivot high/low with symmetric left/right strength 3 or 5; usable only after right-side confirmation hour closes.",
        "breakout": "First 15m close across latest confirmed swing level; next 15m open entry.",
        "retest": "Within next 8 bars, touch broken level and close back in breakout direction; cancel if close crosses back through level; next 15m open entry.",
        "stops": ["breakout candle opposite extreme", "1.0 x 15m Wilder ATR(14)", "1.5 x 15m Wilder ATR(14)"],
        "targets_R": list(TARGETS_R),
        "filters": list(FILTERS),
        "sessions_utc": list(SESSIONS),
        "maximum_holding": "8 hours / 32 15m bars; force exit at last 15m close of horizon",
        "execution": "one position at a time per configuration; same-bar SL/TP resolves SL first; adverse gap-through stop fill; target fills at target; skip any trade with a data gap or incomplete full horizon; skip risk >5% of entry",
        "cost": "Assumed 12bp round-trip deducted as entry * 0.0012 / initial risk; fee tier not verified; no funding or separate spread/slippage model",
        "splits": "Chronological 70% train / 15% validation / 15% OOS; no trade may cross a sample boundary; OOS run only once for validation-selected configuration",
        "selection": "Candidate screen and selection rules are written to selection.json; no OOS selection or tuning",
        "limitations": "Single BTCUSD instrument; UTC buckets are time-of-day bins, not exchange sessions; ATR stop uses signal-candle ATR; simplified mechanical BOS/retest definition; funding omitted",
        "data_quality": data_quality,
    }
    (OUT / "methodology.json").write_text(json.dumps(methodology, indent=2, default=str))

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"CONFIGURATIONS: {len(configs)}")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(train_candidates)}; VALIDATION PASS: {len(eligible_validation)}")
    if selected:
        print("\nVALIDATION-SELECTED CONFIG")
        print(json.dumps({k: v for k, v in selected.items() if k != "signals"}, indent=2))
        print("\nSELECTED OOS SUMMARY")
        print(json.dumps(oos_summary, indent=2, default=str))
        print("\nOOS MONTHLY")
        monthly_path = OUT / "chosen_oos_monthly.csv"
        print(monthly_path.read_text() if monthly_path.exists() else "No monthly trades")
        print("\nOOS UTC BUCKETS")
        bucket_path = OUT / "chosen_oos_utc_buckets.csv"
        print(bucket_path.read_text() if bucket_path.exists() else "No bucket trades")
    else:
        print("NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; OOS WAS NOT EVALUATED.")
    print(f"Artifacts written to {OUT}/")


if __name__ == "__main__":
    main()
