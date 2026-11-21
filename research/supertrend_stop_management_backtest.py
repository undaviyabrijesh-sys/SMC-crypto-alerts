"""BTCUSD Supertrend stop-management sensitivity; experimental only.

Reuses the repository's causal 15m Supertrend implementation, but runs every
contiguous data segment independently so ATR, EMA and Supertrend state cannot
leak across missing candles. Compares fixed signal-line, trailing Supertrend,
ATR and recent-swing initial stops. OOS is evaluated only after train/validation
gates pass.
"""
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch
from supertrend_intraday_backtest import prepare_base, build_supertrend

OUT = Path("supertrend_stop_sensitivity_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD_BARS = 32
PRIMARY_COST_BPS = 12
COSTS_BPS = (6, 12, 20)
SOURCES = ("hl2", "ema50_15m")
ATR_LENGTHS = (7, 10, 14)
ATR_MULTIPLIERS = (2.0, 2.5, 3.0)
STOP_METHODS = ("signal_st", "trailing_st", "atr_1.0", "atr_1.5", "swing_5")
TARGETS_R = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_1h")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 20
MAX_TRAIN_CANDIDATES = 25


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def contiguous_ranges(index):
    if len(index) == 0:
        return []
    breaks = index.to_series().diff().ne(BAR)
    breaks.iloc[0] = False
    ids = breaks.cumsum().to_numpy()
    ranges = []
    start = 0
    for i in range(1, len(ids)):
        if ids[i] != ids[i - 1]:
            ranges.append((start, i))
            start = i
    ranges.append((start, len(ids)))
    return ranges


def prepare_segments(raw):
    raw = raw.sort_index().copy()
    raw = raw[~raw.index.duplicated(keep="last")]
    if raw.empty:
        raise ValueError("No BTC 15m candles")
    for col in ("open", "high", "low", "close"):
        raw[col] = pd.to_numeric(raw[col], errors="raise")
        if not np.isfinite(raw[col].to_numpy(float)).all():
            raise ValueError(f"Non-finite OHLC values in {col}")
    if ((raw.high < raw[["open", "close", "low"]].max(axis=1)) |
        (raw.low > raw[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC candle")

    ranges = contiguous_ranges(raw.index)
    d_parts, tr_parts, segments = [], [], []
    offset = 0
    for segment_id, (lo, hi) in enumerate(ranges):
        part = raw.iloc[lo:hi].copy()
        d_part, tr_part, hourly = prepare_base(part)
        # Compute 1H EMA200 independently within this contiguous segment.
        hourly = hourly.copy()
        hourly["ema200"] = hourly.close.ewm(
            span=200, adjust=False, min_periods=200
        ).mean()
        d_part["ema200_1h"] = hourly.ema200.reindex(
            d_part.index, method="ffill"
        )
        d_part["segment_id"] = segment_id
        d_parts.append(d_part)
        tr_parts.append(tr_part)
        segments.append((offset, offset + len(d_part)))
        offset += len(d_part)

    d = pd.concat(d_parts).sort_index()
    tr = pd.concat(tr_parts).reindex(d.index)
    # Trend regime uses only the last completed 1H EMA context available at
    # each 15m timestamp. Unknown warm-up bars are explicitly labelled.
    bull = (d.close > d.ema50_1h) & (d.ema50_1h > d.ema200_1h)
    bear = (d.close < d.ema50_1h) & (d.ema50_1h < d.ema200_1h)
    d["regime"] = np.select(
        [bull.fillna(False), bear.fillna(False)],
        ["bull", "bear"],
        default="range_or_warmup",
    )
    return d, tr, segments


def ratchet_stop(side, current, candidate):
    if not np.isfinite(candidate):
        return current
    return max(current, candidate) if side == "long" else min(current, candidate)


def resolve_exit(side, open_price, high, low, stop, target):
    """Conservative OHLC exit: stop first, adverse gap at the open."""
    if side == "long":
        if low <= stop:
            return (min(open_price, stop), "SL")
        if high >= target:
            return (target, "TP")
    else:
        if high >= stop:
            return (max(open_price, stop), "SL")
        if low <= target:
            return (target, "TP")
    return None, None


def build_indicator_cache(d, tr, segments):
    cache = {}
    for source, atr_len, multiplier in itertools.product(
        SOURCES, ATR_LENGTHS, ATR_MULTIPLIERS
    ):
        n = len(d)
        atr_all = np.full(n, np.nan)
        direction_all = np.ones(n, dtype=np.int8)
        st_all = np.full(n, np.nan)
        signals = []
        # Crucially, indicator recurrence is restarted for every segment.
        for start, end in segments:
            part = d.iloc[start:end]
            atr, direction, st_line = build_supertrend(
                part, tr.iloc[start:end], source, atr_len, multiplier
            )
            atr_all[start:end] = atr.to_numpy(float)
            direction_all[start:end] = direction
            st_all[start:end] = st_line
            close = part.close.to_numpy(float)
            for i in range(1, len(part) - 1):
                if not np.isfinite(st_line[i]) or not np.isfinite(st_line[i - 1]):
                    continue
                long_flip = direction[i - 1] == 1 and direction[i] == -1
                short_flip = direction[i - 1] == -1 and direction[i] == 1
                if not (long_flip or short_flip):
                    continue
                signals.append({
                    "signal_i": start + i,
                    "entry_i": start + i + 1,
                    "side": "long" if long_flip else "short",
                    "stop_line": float(st_line[i]),
                    "signal_close": float(close[i]),
                    "atr_signal": float(atr.iloc[i]),
                })
        cache[(source, atr_len, multiplier)] = {
            "signals": signals,
            "atr": atr_all,
            "direction": direction_all,
            "st_line": st_all,
        }
    return cache


def in_session(ts, session):
    return session == "all" or 7 <= ts.hour < 19


def max_losing_streak(values):
    current = maximum = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum


def metrics(trades):
    if trades.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "positive_month_fraction": 0.0,
        }
    g = trades.sort_values("entry_time")
    r = g.net_R.astype(float)
    wins, losses = r[r > 0], r[r < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) else (
        float("inf") if len(wins) else 0.0
    )
    equity = np.r_[0.0, r.cumsum().to_numpy()]
    dd = equity[1:] - np.maximum.accumulate(equity)[1:]
    monthly = g.assign(month=g.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(g)),
        "win_rate_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else 999.0,
        "net_R": round(float(r.sum()), 3),
        "avg_R": round(float(r.mean()), 4),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 3),
        "max_losing_streak": int(max_losing_streak(r.to_numpy())),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3) if len(monthly) else 0.0,
    }


def simulate(d, signals, config, start_i, end_i, gap_mask,
             atr_all, st_all, cost_bps=PRIMARY_COST_BPS):
    opens = d.open.to_numpy(float)
    highs = d.high.to_numpy(float)
    lows = d.low.to_numpy(float)
    closes = d.close.to_numpy(float)
    ema1h = d.ema50_1h.to_numpy(float)
    regimes = d.regime.to_numpy()
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
        atr_signal = float(atr_all[signal_i])
        if not np.isfinite(atr_signal) or atr_signal <= 0:
            continue
        method = config["stop_method"]
        if method in ("signal_st", "trailing_st"):
            initial_stop = float(sig["stop_line"])
        elif method == "atr_1.0":
            initial_stop = entry - atr_signal if side == "long" else entry + atr_signal
        elif method == "atr_1.5":
            distance = 1.5 * atr_signal
            initial_stop = entry - distance if side == "long" else entry + distance
        elif method == "swing_5":
            if signal_i < 4:
                continue
            pad = 0.1 * atr_signal
            if side == "long":
                initial_stop = float(np.min(lows[signal_i - 4:signal_i + 1]) - pad)
            else:
                initial_stop = float(np.max(highs[signal_i - 4:signal_i + 1]) + pad)
        else:
            raise ValueError(f"Unknown stop method: {method}")

        risk = entry - initial_stop if side == "long" else initial_stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry + config["target_r"] * risk if side == "long" else entry - config["target_r"] * risk

        stop = initial_stop
        outcome = "TIME"
        exit_i = entry_i + MAX_HOLD_BARS - 1
        exit_price = float(closes[exit_i])
        for j in range(entry_i, entry_i + MAX_HOLD_BARS):
            # Trailing update uses only the previous, already completed 15m bar.
            if method == "trailing_st" and j > entry_i:
                stop = ratchet_stop(side, stop, st_all[j - 1])
            fill, reason = resolve_exit(
                side, float(opens[j]), float(highs[j]), float(lows[j]), stop, target
            )
            if reason:
                outcome, exit_price, exit_i = reason, float(fill), j
                break

        gross_r = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        cost_r = entry * (cost_bps / 10000.0) / risk
        rows.append({
            "signal_time": idx[signal_i], "entry_time": idx[entry_i],
            "exit_time": idx[exit_i], "side": side, "regime": regimes[signal_i],
            "stop_method": method, "target_r": config["target_r"],
            "entry": entry, "initial_stop": initial_stop, "final_stop": stop,
            "risk": risk, "target": target, "exit": exit_price,
            "outcome": outcome, "gross_R": gross_r,
            "estimated_cost_R": cost_r, "net_R": gross_r - cost_r,
            "cost_bps": cost_bps,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def monthly_summary(trades):
    if trades.empty:
        return pd.DataFrame()
    g = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"))
    return g.groupby("month").agg(
        trades=("net_R", "size"),
        win_rate_pct=("net_R", lambda x: float((x > 0).mean() * 100)),
        net_R=("net_R", "sum"),
    ).reset_index()


def regime_summary(trades):
    if trades.empty:
        return pd.DataFrame()
    return trades.groupby("regime").agg(
        trades=("net_R", "size"),
        win_rate_pct=("net_R", lambda x: float((x > 0).mean() * 100)),
        net_R=("net_R", "sum"),
        avg_R=("net_R", "mean"),
    ).reset_index()


def add_cost_sensitivity(rows, label, split_name, trades):
    if trades.empty:
        return
    for bps in COSTS_BPS:
        t = trades.copy()
        t["net_R"] = t.gross_R - t.entry * (bps / 10000.0) / t.risk
        rows.append({
            "candidate": label, "split": split_name, "cost_bps": bps,
            **metrics(t),
        })


def main():
    raw = fetch("15m")
    d, tr, segments = prepare_segments(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m history: {len(d)} rows")

    diffs = d.index.to_series().diff()
    gap_mask = diffs.ne(BAR).to_numpy(copy=True)
    gap_mask[0] = False
    data_path = OUT / "BTCUSD_15m.csv"
    d.to_csv(data_path)
    n = len(d)
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    split_bounds = {
        "train": (0, train_end),
        "validation": (train_end, validation_end),
        "oos": (validation_end, n),
    }
    data_quality = {
        "symbol": "BTCUSD", "timeframe": "15m", "rows": int(n),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps": int((diffs.dropna() != BAR).sum()), "segments": len(segments),
        "largest_gap_minutes": float(diffs.dropna().max().total_seconds() / 60) if len(diffs.dropna()) else 0.0,
        "sha256": sha256(data_path),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[validation_end]),
        "oos_start_utc": str(d.index[validation_end]),
    }
    (OUT / "data_quality.json").write_text(json.dumps(data_quality, indent=2))

    cache = build_indicator_cache(d, tr, segments)
    gap_mask[0] = False
    matrix_rows = []
    trade_cache = {}
    for (source, atr_len, multiplier), indicator in cache.items():
        for stop_method, target, filt, direction, session in itertools.product(
            STOP_METHODS, TARGETS_R, FILTERS, DIRECTIONS, SESSIONS
        ):
            cid = (
                f"{source}_atr{atr_len}_x{str(multiplier).replace('.', 'p')}_"
                f"{stop_method}_{str(target).replace('.', 'p')}R_{filt}_{direction}_{session}"
            )
            config = {
                "config_id": cid, "source": source, "atr_length": atr_len,
                "atr_multiplier": multiplier, "stop_method": stop_method,
                "target_r": target, "filter": filt, "direction": direction,
                "session": session,
            }
            base = dict(config)
            train = simulate(
                d, indicator["signals"], config, *split_bounds["train"], gap_mask,
                indicator["atr"], indicator["st_line"], PRIMARY_COST_BPS
            )
            validation = simulate(
                d, indicator["signals"], config, *split_bounds["validation"], gap_mask,
                indicator["atr"], indicator["st_line"], PRIMARY_COST_BPS
            )
            mt, mv = metrics(train), metrics(validation)
            matrix_rows.append({
                **base,
                **{f"train_{k}": v for k, v in mt.items()},
                **{f"validation_{k}": v for k, v in mv.items()},
            })
            trade_cache[cid] = (train, validation, config, indicator)

    matrix = pd.DataFrame(matrix_rows)
    matrix.to_csv(OUT / "matrix.csv", index=False)
    train_ok = (
        (matrix.train_trades >= MIN_TRAIN_TRADES)
        & (matrix.train_net_R > 0)
        & (matrix.train_profit_factor >= 1.05)
        & (matrix.train_max_drawdown_R >= -25.0)
        & (matrix.train_positive_month_fraction >= 0.50)
    )
    eligible_train = matrix[train_ok].copy()
    if not eligible_train.empty:
        eligible_train["train_quality"] = (
            eligible_train.train_net_R /
            eligible_train.train_max_drawdown_R.abs().clip(lower=1.0)
        )
        shortlist = eligible_train.sort_values(
            ["train_quality", "train_trades"], ascending=[False, False]
        ).head(MAX_TRAIN_CANDIDATES)
        validation_ok = (
            (shortlist.validation_trades >= MIN_VALIDATION_TRADES)
            & (shortlist.validation_net_R > 0)
            & (shortlist.validation_profit_factor >= 1.05)
            & (shortlist.validation_max_drawdown_R >= -15.0)
            & (shortlist.validation_positive_month_fraction >= 0.50)
        )
        eligible_validation = shortlist[validation_ok].copy()
    else:
        shortlist = pd.DataFrame()
        eligible_validation = pd.DataFrame()

    top_train = matrix.sort_values("train_net_R", ascending=False).head(5)
    top_validation = matrix[matrix.validation_trades >= MIN_VALIDATION_TRADES].sort_values(
        "validation_net_R", ascending=False
    ).head(5)
    top_train.to_csv(OUT / "top_train.csv", index=False)
    top_validation.to_csv(OUT / "top_validation_min20.csv", index=False)

    diagnostic_sets = {}
    if not top_train.empty:
        cid = top_train.iloc[0].config_id
        trn, val, config, indicator = trade_cache[cid]
        trn.to_csv(OUT / "best_train_trades.csv", index=False)
        val.to_csv(OUT / "best_train_matching_validation_trades.csv", index=False)
        monthly_summary(trn).to_csv(OUT / "best_train_monthly.csv", index=False)
        monthly_summary(val).to_csv(OUT / "best_train_matching_validation_monthly.csv", index=False)
        regime_summary(trn).to_csv(OUT / "best_train_regimes.csv", index=False)
        regime_summary(val).to_csv(OUT / "best_train_matching_validation_regimes.csv", index=False)
        diagnostic_sets["best_train"] = (trn, val)

    if not top_validation.empty:
        cid = top_validation.iloc[0].config_id
        trn, val, config, indicator = trade_cache[cid]
        trn.to_csv(OUT / "best_validation_candidate_training_trades.csv", index=False)
        val.to_csv(OUT / "best_validation_candidate_trades.csv", index=False)
        monthly_summary(trn).to_csv(OUT / "best_validation_candidate_training_monthly.csv", index=False)
        monthly_summary(val).to_csv(OUT / "best_validation_candidate_monthly.csv", index=False)
        regime_summary(trn).to_csv(OUT / "best_validation_candidate_training_regimes.csv", index=False)
        regime_summary(val).to_csv(OUT / "best_validation_candidate_regimes.csv", index=False)
        diagnostic_sets["best_validation_min20"] = (trn, val)

    sensitivity = []
    for label, (trn, val) in diagnostic_sets.items():
        add_cost_sensitivity(sensitivity, label, "train", trn)
        add_cost_sensitivity(sensitivity, label, "validation", val)
    pd.DataFrame(sensitivity).to_csv(OUT / "cost_sensitivity.csv", index=False)

    oos_summary = {}
    if not eligible_validation.empty:
        eligible_validation = eligible_validation.copy()
        eligible_validation["validation_quality"] = (
            eligible_validation.validation_net_R /
            eligible_validation.validation_max_drawdown_R.abs().clip(lower=1.0)
        )
        selected = eligible_validation.sort_values(
            ["validation_quality", "validation_trades"], ascending=[False, False]
        ).iloc[0]
        cid = selected.config_id
        _, _, config, indicator = trade_cache[cid]
        oos = simulate(
            d, indicator["signals"], config, *split_bounds["oos"], gap_mask,
            indicator["atr"], indicator["st_line"], PRIMARY_COST_BPS
        )
        oos.to_csv(OUT / "selected_oos_trades.csv", index=False)
        monthly_summary(oos).to_csv(OUT / "selected_oos_monthly.csv", index=False)
        regime_summary(oos).to_csv(OUT / "selected_oos_regimes.csv", index=False)
        oos_summary = metrics(oos)
        pd.DataFrame([oos_summary | {"config_id": cid}]).to_csv(
            OUT / "selected_oos_summary.csv", index=False
        )
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered training and validation gates; OOS was not evaluated.\n"
        )

    meta = {
        **data_quality,
        "configurations": len(matrix),
        "train_eligible": int(len(eligible_train)),
        "train_shortlist": int(len(shortlist)),
        "validation_pass": int(len(eligible_validation)),
        "oos_evaluated": bool(not eligible_validation.empty),
        "oos_summary": oos_summary,
        "primary_cost_bps": PRIMARY_COST_BPS,
        "cost_sensitivity_bps": list(COSTS_BPS),
        "cost_assumption": "assumed round-trip cost on one BTC leg; account fee tier, separate spread/market impact and funding are unverified/excluded",
        "execution": "15m confirmed Supertrend flip; next 15m open; signal-line, trailing-line, ATR or prior-5-bar swing stop; fixed 1.5R/2R/3R target; 8h max hold; same-bar SL first; adverse stop gaps at worse open",
        "indicator": "existing TradingView-style Supertrend helper; Wilder RMA ATR; HL2 or 15m EMA50; ATR length 7/10/14; multiplier 2/2.5/3",
        "gap_handling": "split raw data into contiguous 15m segments; recompute 15m EMA, completed-1H EMA50/EMA200 and Supertrend independently in each segment; no state carries across gaps",
        "split": "chronological 70/15/15; train >=40 trades, PF>=1.05, net R>0, DD>=-25R, >=50% positive months; validation >=20, PF>=1.05, net R>0, DD>=-15R, >=50% positive months; OOS only after both gates",
        "matrix": "2 sources x 3 ATR lengths x 3 multipliers x 5 stop methods x 3 targets x 2 HTF filters x 3 direction modes x 2 sessions",
        "stop_methods": list(STOP_METHODS),
        "limitations": ["15m OHLC only; no order-book spread or market-impact model.",
                        "12bp primary cost is assumed, not account-tier verified; no funding for positions capped at 8h.",
                        "UTC 07-19 session is a fixed UTC bucket and does not adjust for DST.",
                        "Trailing Supertrend updates use only the prior completed 15m line; same-bar SL is prioritized over target."] ,
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2))

    print("DATA QUALITY")
    print(json.dumps(data_quality, indent=2))
    print(f"CONFIGURATIONS: {len(matrix)}")
    print(f"TRAIN ELIGIBLE: {len(eligible_train)}; SHORTLIST: {len(shortlist)}; VALIDATION PASS: {len(eligible_validation)}")
    print("TOP TRAIN")
    print(top_train[["config_id", "train_trades", "train_win_rate_pct",
                     "train_profit_factor", "train_net_R", "train_max_drawdown_R",
                     "train_max_losing_streak", "train_positive_month_fraction"]].to_string(index=False))
    print("TOP VALIDATION (minimum 20 trades)")
    print(top_validation[["config_id", "validation_trades", "validation_win_rate_pct",
                          "validation_profit_factor", "validation_net_R",
                          "validation_max_drawdown_R", "validation_max_losing_streak",
                          "validation_positive_month_fraction"]].to_string(index=False))
    if eligible_validation.empty:
        print("NO CONFIGURATION PASSED TRAIN/VALIDATION; OOS NOT EVALUATED.")
    else:
        print("SELECTED OOS SUMMARY")
        print(json.dumps(oos_summary, indent=2))
    print(f"Artifacts written to {OUT}/")


def self_test():
    idx_a = pd.date_range("2025-01-01 00:00", periods=240, freq="15min", tz="UTC")
    idx_b = pd.date_range("2025-01-04 00:00", periods=240, freq="15min", tz="UTC")
    idx = idx_a.append(idx_b)
    close = np.r_[100.0 + np.arange(240) * 0.1, 200.0 + np.arange(240) * 0.1]
    raw = pd.DataFrame({
        "open": close, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": np.ones(len(close)),
    }, index=idx)
    d, tr, segments = prepare_segments(raw)
    assert len(segments) == 2
    second = segments[1][0]
    assert np.isclose(tr.iloc[second], d.high.iloc[second] - d.low.iloc[second])
    assert np.isclose(d.ema50_15m.iloc[second], d.close.iloc[second])
    assert pd.isna(d.ema50_1h.iloc[second]), "stale 1H EMA must not cross the gap"
    atr, direction, st_line = build_supertrend(
        d.iloc[second:], tr.iloc[second:], "hl2", 7, 2.0
    )
    valid = np.flatnonzero(np.isfinite(atr.to_numpy(float)))
    assert len(valid) and direction[valid[0]] == 1, "Supertrend state must reset at segment start"

    assert ratchet_stop("long", 90.0, 95.0) == 95.0
    assert ratchet_stop("long", 95.0, 92.0) == 95.0
    assert ratchet_stop("short", 110.0, 105.0) == 105.0
    assert ratchet_stop("short", 105.0, 108.0) == 105.0
    assert resolve_exit("long", 100, 120, 80, 90, 110) == (90, "SL")
    assert resolve_exit("long", 85, 95, 80, 90, 110) == (85, "SL")
    assert resolve_exit("short", 115, 120, 112, 110, 90) == (115, "SL")
    assert resolve_exit("short", 100, 120, 80, 110, 90) == (110, "SL")
    assert resolve_exit("long", 115, 120, 112, 90, 110) == (110, "TP")
    print("10 gap, indicator-reset, stop-ratchet and execution self-tests passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test()
    else:
        main()
