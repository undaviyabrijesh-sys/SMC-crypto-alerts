"""Intraday BTCUSD EMA pullback continuation research.

15m entries after a confirmed EMA pullback/rejection. Trend context comes
from completed 1H bars only. Maximum hold is 8 hours. A chronological
train/validation/OOS funnel selects at most one configuration before OOS.
Research only; this module never places orders or sends alerts.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("ema_pullback_intraday_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32  # 8 hours
PULLBACK_EMAS = (20, 50)
CONFIRMATIONS = ("previous_bar_break", "engulfing")
FILTERS = ("ema50_price", "ema50_slope", "ema50_slope_ema200")
STOPS = ("signal_extreme", "atr1", "atr1p5")
TARGETS_R = (1.5, 2.0, 3.0)
SESSIONS = ("all", "00-07", "07-13", "13-19", "19-24")
PULLBACK_TOLERANCE_ATR = 0.15
COST_RATE = 0.0012  # assumed 12bp round trip; not fee-tier verified
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MAX_TRAIN_CANDIDATES = 25


def prepare_data(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    prev_close = d.close.shift(1)
    tr = pd.concat(
        [
            d.high - d.low,
            (d.high - prev_close).abs(),
            (d.low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr15"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    for length in PULLBACK_EMAS:
        d[f"ema{length}_15m"] = d.close.ewm(
            span=length, adjust=False, min_periods=length
        ).mean()

    hourly = d.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = d.close.resample("1h", label="right", closed="left").count()
    hourly = hourly.loc[counts.reindex(hourly.index).eq(4)].dropna()
    for length in (50, 200):
        hourly[f"ema{length}"] = hourly.close.ewm(
            span=length, adjust=False, min_periods=length
        ).mean()

    # Right-labelled hourly bars are available only at their closing timestamp.
    for col in ("close", "ema50", "ema200"):
        d[f"{col}_1h"] = hourly[col].reindex(d.index, method="ffill")
    d["ema50_rising_1h"] = (
        hourly.ema50 > hourly.ema50.shift(4)
    ).reindex(d.index, method="ffill").fillna(False)
    d["ema50_falling_1h"] = (
        hourly.ema50 < hourly.ema50.shift(4)
    ).reindex(d.index, method="ffill").fillna(False)
    return d, hourly


def trend_allowed(d, side, filter_name):
    close = d.close_1h.to_numpy(dtype=float)
    ema50 = d.ema50_1h.to_numpy(dtype=float)
    ema200 = d.ema200_1h.to_numpy(dtype=float)
    rising = d.ema50_rising_1h.to_numpy(dtype=bool)
    falling = d.ema50_falling_1h.to_numpy(dtype=bool)
    if side == "long":
        allowed = np.isfinite(close) & np.isfinite(ema50) & (close > ema50)
        if filter_name in ("ema50_slope", "ema50_slope_ema200"):
            allowed &= rising
        if filter_name == "ema50_slope_ema200":
            allowed &= np.isfinite(ema200) & (close > ema200)
    else:
        allowed = np.isfinite(close) & np.isfinite(ema50) & (close < ema50)
        if filter_name in ("ema50_slope", "ema50_slope_ema200"):
            allowed &= falling
        if filter_name == "ema50_slope_ema200":
            allowed &= np.isfinite(ema200) & (close < ema200)
    return allowed


def build_signals(d, ema_length, confirmation, filter_name):
    """Signal uses only the just-closed 15m candle and completed 1H context."""
    o = d.open.to_numpy(dtype=float)
    h = d.high.to_numpy(dtype=float)
    l = d.low.to_numpy(dtype=float)
    c = d.close.to_numpy(dtype=float)
    atr = d.atr15.to_numpy(dtype=float)
    ema = d[f"ema{ema_length}_15m"].to_numpy(dtype=float)
    tolerance = PULLBACK_TOLERANCE_ATR * atr

    prev_h = np.r_[np.nan, h[:-1]]
    prev_l = np.r_[np.nan, l[:-1]]
    prev_o = np.r_[np.nan, o[:-1]]
    prev_c = np.r_[np.nan, c[:-1]]

    if confirmation == "previous_bar_break":
        bull_confirm = c > prev_h
        bear_confirm = c < prev_l
    else:
        bull_confirm = (c > o) & (prev_c < prev_o) & (o <= prev_c) & (c >= prev_o)
        bear_confirm = (c < o) & (prev_c > prev_o) & (o >= prev_c) & (c <= prev_o)

    valid = (
        np.isfinite(ema)
        & np.isfinite(atr)
        & (atr > 0)
        & np.isfinite(tolerance)
    )
    long_pullback = (
        valid
        & (np.abs(l - ema) <= tolerance)
        & (c > ema)
        & bull_confirm
        & trend_allowed(d, "long", filter_name)
    )
    short_pullback = (
        valid
        & (np.abs(h - ema) <= tolerance)
        & (c < ema)
        & bear_confirm
        & trend_allowed(d, "short", filter_name)
    )

    signals = []
    for i in np.flatnonzero(long_pullback | short_pullback):
        if i < 1 or i + 1 >= len(d):
            continue
        side = "long" if long_pullback[i] else "short"
        signals.append(
            {
                "signal_i": int(i),
                "entry_i": int(i + 1),
                "side": side,
                "signal_extreme": float(l[i] if side == "long" else h[i]),
                "atr_signal": float(atr[i]),
            }
        )
    return signals


def in_session(ts, session):
    if session == "all":
        return True
    ranges = {
        "00-07": (0, 7),
        "07-13": (7, 13),
        "13-19": (13, 19),
        "19-24": (19, 24),
    }
    lo, hi = ranges[session]
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
            "trades": 0,
            "profitable_pct": 0.0,
            "profit_factor": None,
            "net_R": 0.0,
            "avg_R": 0.0,
            "max_drawdown_R": 0.0,
            "max_losing_streak": 0,
            "TP": 0,
            "SL": 0,
            "TIME": 0,
            "positive_month_fraction": 0.0,
        }
    g = trades.sort_values("entry_time")
    r = g.net_R.astype(float)
    wins = r[r > 0]
    losses = r[r < 0]
    equity = r.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    drawdown = equity - peak
    monthly = (
        g.assign(month=g.entry_time.dt.strftime("%Y-%m"))
        .groupby("month").net_R.sum()
    )
    return {
        "trades": int(len(g)),
        "profitable_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": (
            round(float(wins.sum() / abs(losses.sum())), 3)
            if len(losses) and abs(losses.sum()) > 0
            else None
        ),
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, drawdown.min())), 2),
        "max_losing_streak": int(max_losing_streak(r.to_numpy())),
        "TP": int((g.outcome == "TP").sum()),
        "SL": int((g.outcome == "SL").sum()),
        "TIME": int((g.outcome == "TIME").sum()),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3)
        if len(monthly) else 0.0,
    }


def simulate(d, signals, config, start_i, end_i, gap_mask):
    o = d.open.to_numpy(dtype=float)
    h = d.high.to_numpy(dtype=float)
    l = d.low.to_numpy(dtype=float)
    c = d.close.to_numpy(dtype=float)
    idx = d.index
    trades = []
    last_exit_i = -1

    for sig in signals:
        signal_i = sig["signal_i"]
        entry_i = sig["entry_i"]
        if entry_i < start_i or entry_i >= end_i:
            continue
        if entry_i <= last_exit_i:
            continue
        if entry_i + MAX_HOLD_BARS > end_i:
            continue
        if not in_session(idx[entry_i], config["session"]):
            continue
        # Include the signal-to-entry transition and every bar in the holding window.
        if gap_mask[signal_i : entry_i + MAX_HOLD_BARS].any():
            continue

        side = sig["side"]
        entry = float(o[entry_i])
        if config["stop"] == "signal_extreme":
            stop = sig["signal_extreme"]
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
        exit_i = entry_i + MAX_HOLD_BARS - 1
        exit_price = float(c[exit_i])
        for j in range(entry_i, entry_i + MAX_HOLD_BARS):
            stop_hit = l[j] <= stop if side == "long" else h[j] >= stop
            target_hit = h[j] >= target if side == "long" else l[j] <= target
            if stop_hit:  # conservative same-candle ambiguity: stop first
                outcome = "SL"
                exit_price = (
                    min(stop, float(o[j]))
                    if side == "long"
                    else max(stop, float(o[j]))
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
        trades.append(
            {
                "signal_time": idx[signal_i],
                "entry_time": idx[entry_i],
                "exit_time": idx[exit_i],
                "side": side,
                "pullback_ema": config["ema_length"],
                "confirmation": config["confirmation"],
                "filter": config["filter"],
                "session": config["session"],
                "entry": entry,
                "stop": stop,
                "target": target,
                "exit": exit_price,
                "outcome": outcome,
                "gross_R": gross_r,
                "estimated_cost_R": cost_r,
                "net_R": gross_r - cost_r,
            }
        )
        last_exit_i = exit_i
    return pd.DataFrame(trades)


def make_config_id(ema_length, confirmation, filt, stop, target, session):
    target_text = str(target).replace(".", "p")
    return (
        f"ema{ema_length}_{confirmation}_{filt}_{stop}_"
        f"{target_text}R_{session}"
    )


def main():
    raw = fetch("15m")
    d, hourly = prepare_data(raw)
    if len(d) < 15000:
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
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "rows": int(len(d)),
        "start_utc": str(d.index.min()),
        "end_utc": str(d.index.max()),
        "gaps": int((diffs.dropna() != BAR).sum()),
        "largest_gap_minutes": float(diffs.dropna().max().total_seconds() / 60),
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "complete_hourly_bars": int(len(hourly)),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    # Cache causal signals; stops, targets and session constraints are simulated later.
    signal_cache = {}
    configs = []
    for ema_length, confirmation, filt in itertools.product(
        PULLBACK_EMAS, CONFIRMATIONS, FILTERS
    ):
        signal_cache[(ema_length, confirmation, filt)] = build_signals(
            d, ema_length, confirmation, filt
        )

    for ema_length, confirmation, filt, stop, target, session in itertools.product(
        PULLBACK_EMAS, CONFIRMATIONS, FILTERS, STOPS, TARGETS_R, SESSIONS
    ):
        key = (ema_length, confirmation, filt)
        configs.append(
            {
                "config_id": make_config_id(
                    ema_length, confirmation, filt, stop, target, session
                ),
                "ema_length": ema_length,
                "confirmation": confirmation,
                "filter": filt,
                "stop": stop,
                "target_r": target,
                "session": session,
                "signals": signal_cache[key],
            }
        )

    train_rows = []
    validation_rows = []
    for config in configs:
        base = {k: v for k, v in config.items() if k != "signals"}
        for sample in ("train", "validation"):
            trades = simulate(
                d, config["signals"], config, *segments[sample], gap_mask
            )
            result = base | {"sample": sample} | metrics(trades)
            if sample == "train":
                train_rows.append(result)
            else:
                validation_rows.append(result)

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
            eligible_train.net_R
            / eligible_train.max_drawdown_R.abs().clip(lower=1.0)
        )
        shortlist = eligible_train.sort_values(
            ["train_quality", "trades"], ascending=[False, False]
        ).head(MAX_TRAIN_CANDIDATES)
        eligible_validation = validation_df[
            validation_df.config_id.isin(shortlist.config_id)
            & (validation_df.trades >= MIN_VALIDATION_TRADES)
            & (validation_df.net_R > 0)
            & (validation_df.profit_factor >= 1.05)
            & (validation_df.max_drawdown_R >= -15.0)
            & (validation_df.positive_month_fraction >= 0.50)
        ].copy()
    else:
        shortlist = pd.DataFrame()
        eligible_validation = pd.DataFrame()

    selected = None
    oos_trades = pd.DataFrame()
    oos_summary = None
    if not eligible_validation.empty:
        eligible_validation["validation_quality"] = (
            eligible_validation.net_R
            / eligible_validation.max_drawdown_R.abs().clip(lower=1.0)
        )
        chosen = eligible_validation.sort_values(
            ["validation_quality", "trades"], ascending=[False, False]
        ).iloc[0]
        selected = next(
            config for config in configs if config["config_id"] == chosen.config_id
        )
        oos_trades = simulate(
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
                .agg(
                    trades=("net_R", "size"),
                    net_R=("net_R", "sum"),
                    profitable_pct=("net_R", lambda x: (x > 0).mean() * 100),
                )
            )
            monthly.to_csv(OUT / "chosen_oos_monthly.csv", index=False)
            side_rows = []
            for side, group in oos_trades.groupby("side"):
                side_rows.append({"side": side} | metrics(group))
            pd.DataFrame(side_rows).to_csv(
                OUT / "chosen_oos_sides.csv", index=False
            )
            bucket_rows = []
            oos_trades = oos_trades.copy()
            oos_trades["utc_bucket"] = oos_trades.entry_time.dt.hour.map(
                lambda hour: (
                    "00-07" if hour < 7 else
                    "07-13" if hour < 13 else
                    "13-19" if hour < 19 else "19-24"
                )
            )
            for bucket, group in oos_trades.groupby("utc_bucket"):
                bucket_rows.append({"utc_bucket": bucket} | metrics(group))
            pd.DataFrame(bucket_rows).to_csv(
                OUT / "chosen_oos_utc_buckets.csv", index=False
            )
        else:
            for name, columns in (
                ("chosen_oos_monthly.csv", ["month", "trades", "net_R"]),
                ("chosen_oos_sides.csv", ["side", "trades", "net_R"]),
                ("chosen_oos_utc_buckets.csv", ["utc_bucket", "trades", "net_R"]),
            ):
                pd.DataFrame(columns=columns).to_csv(OUT / name, index=False)
    else:
        for name, columns in (
            ("chosen_oos_trades.csv", []),
            ("chosen_oos_monthly.csv", ["month", "trades", "net_R"]),
            ("chosen_oos_sides.csv", ["side", "trades", "net_R"]),
            ("chosen_oos_utc_buckets.csv", ["utc_bucket", "trades", "net_R"]),
        ):
            pd.DataFrame(columns=columns).to_csv(OUT / name, index=False)

    selection = {
        "configuration_count": len(configs),
        "train_eligible_count": int(len(eligible_train)),
        "train_shortlist_count": int(len(shortlist)),
        "validation_pass_count": int(len(eligible_validation)),
        "selected_config": (
            {k: v for k, v in selected.items() if k != "signals"}
            if selected else None
        ),
        "selected_oos_summary": oos_summary,
        "selection_rule": (
            "Train: >=40 trades, net_R>0, PF>=1.05, max DD>=-25R; shortlist top "
            "25 by net_R/abs(maxDD). Validation: >=20 trades, net_R>0, PF>=1.05, "
            "max DD>=-15R, positive in >=50% of active months; select highest "
            "validation net_R/abs(maxDD). Evaluate OOS once for the single "
            "validation-selected configuration only; otherwise do not inspect OOS."
        ),
    }
    (OUT / "selection.json").write_text(json.dumps(selection, indent=2, default=str))

    methodology = {
        "hypothesis": (
            "A 15m pullback to EMA20 or EMA50 followed by directional rejection "
            "may continue in the direction of a completed-1H EMA50 trend."
        ),
        "trend": (
            "Completed 1H close above/below EMA50; filters compare price-only, "
            "EMA50 slope versus four completed 1H bars earlier, or slope plus "
            "completed-1H EMA200 alignment. No unfinished 1H candle is used."
        ),
        "pullback": (
            "Signal candle low (long) or high (short) is within 0.15 x 15m ATR(14) "
            "of EMA20 or EMA50, and the candle closes back on the trend side."
        ),
        "confirmations": {
            "previous_bar_break": "Long close above prior 15m high; short close below prior 15m low.",
            "engulfing": "Strict bullish/bearish body engulfing of prior opposite body.",
        },
        "entry": "Next 15m open after the confirmed signal candle closes.",
        "stops": [
            "Signal-candle low/high",
            "1.0 x signal-candle 15m ATR(14) from entry",
            "1.5 x signal-candle 15m ATR(14) from entry",
        ],
        "targets_R": list(TARGETS_R),
        "sessions_utc": list(SESSIONS),
        "maximum_holding": "8 hours / 32 15m bars; force exit at the last 15m close in the horizon.",
        "execution": (
            "One position at a time per configuration; same-bar SL/TP ambiguity "
            "resolves SL first; adverse gap-through stop fill; target fills at "
            "target; skip data-gap and sample-boundary-crossing trades; reject "
            "initial stop distances above 5% of entry."
        ),
        "cost": (
            "Assumed 12bp round-trip deducted as entry * 0.0012 / initial risk; "
            "fee tier not verified; funding and separate spread/slippage are not modelled."
        ),
        "splits": (
            "Chronological 70% train / 15% validation / 15% OOS. Train shortlist "
            "and validation selection only; evaluate OOS once for one selected "
            "configuration. If no validation pass, OOS is not evaluated."
        ),
        "limitations": (
            "Single BTCUSD instrument; UTC time buckets are not exchange sessions; "
            "mechanical EMA touch/engulfing definitions; funding omitted; no "
            "portfolio-level correlation or leverage model."
        ),
        "data_quality": data_quality,
    }
    (OUT / "methodology.json").write_text(
        json.dumps(methodology, indent=2, default=str)
    )

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"CONFIGURATIONS: {len(configs)}")
    print(
        f"TRAIN ELIGIBLE: {len(eligible_train)}; "
        f"SHORTLIST: {len(shortlist)}; "
        f"VALIDATION PASS: {len(eligible_validation)}"
    )
    if selected:
        print("\nVALIDATION-SELECTED CONFIG")
        print(json.dumps({k: v for k, v in selected.items() if k != "signals"}, indent=2))
        print("\nSELECTED OOS SUMMARY")
        print(json.dumps(oos_summary, indent=2, default=str))
        for label, filename in (
            ("OOS MONTHLY", "chosen_oos_monthly.csv"),
            ("OOS LONG/SHORT", "chosen_oos_sides.csv"),
            ("OOS UTC BUCKETS", "chosen_oos_utc_buckets.csv"),
        ):
            print(f"\n{label}")
            print((OUT / filename).read_text())
    else:
        print(
            "NO CONFIGURATION PASSED THE PRE-REGISTERED TRAIN/VALIDATION FILTERS; "
            "OOS WAS NOT EVALUATED."
        )
    print(f"Artifacts written to {OUT}/")


if __name__ == "__main__":
    main()
