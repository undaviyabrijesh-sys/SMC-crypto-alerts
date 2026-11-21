"""BTCUSD 15m prior-day/confirmed-4h support-resistance rejection study.

Research-only. Levels are exposed only after their source period is complete.
No level, indicator, trade or rolling window crosses a data gap. OOS is touched
only if a candidate passes the preregistered training and validation gates.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("support_resistance_rejection_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
H1 = pd.Timedelta("1h")
H4 = pd.Timedelta("4h")
DAY = pd.Timedelta("1D")
MAX_HOLD = 32
COSTS = (6, 12, 20)
PRIMARY_COST = 12
LEVEL_SOURCES = ("prior_day", "confirmed_4h")
APPROACHES = ("sweep_reclaim", "near_reject")
TOLERANCES = (0.0, 0.1)
CONFIRMATIONS = ("signal_close", "next_bar_break")
BUFFERS = (0.0, 0.1)
TARGETS = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN = 40
MIN_VALIDATION = 20
MAX_SHORTLIST = 25


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate_ohlc(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    for col in ("open", "high", "low", "close"):
        d[col] = pd.to_numeric(d[col], errors="raise")
        if not np.isfinite(d[col].to_numpy(float)).all():
            raise ValueError(f"non-finite {col}")
    bad = (
        (d.high < d[["open", "close", "low"]].max(axis=1))
        | (d.low > d[["open", "close", "high"]].min(axis=1))
        | (d[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if bad.any():
        raise ValueError(f"invalid OHLC rows: {int(bad.sum())}")
    return d


def add_segments(d):
    d = d.copy()
    d["segment"] = d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    return d


def wilder_atr_segment(g, length=14):
    prev = g.close.shift(1)
    tr = pd.concat(
        [g.high - g.low, (g.high - prev).abs(), (g.low - prev).abs()],
        axis=1,
    ).max(axis=1)
    values = tr.to_numpy(float)
    out = np.full(len(values), np.nan)
    if len(values) >= length and np.isfinite(values[:length]).all():
        out[length - 1] = float(values[:length].mean())
        for i in range(length, len(values)):
            out[i] = (out[i - 1] * (length - 1) + values[i]) / length
    return pd.Series(out, index=g.index)


def complete_resample(d, rule, expected_count, expected_step, label):
    x = d[["open", "high", "low", "close"]].resample(
        rule, label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample(rule, label="right", closed="left").count()
    segs = d.segment.resample(rule, label="right", closed="left").nunique()
    source_segment = d.segment.resample(
        rule, label="right", closed="left"
    ).first()
    valid = counts.eq(expected_count) & segs.eq(1)
    x = x.loc[valid].dropna().copy()
    x["source_segment"] = source_segment.reindex(x.index).astype(int)
    dif = x.index.to_series().diff()
    x["bar_segment"] = dif.ne(expected_step).cumsum().astype(int)
    return x


def prior_day_levels(d):
    """Previous complete UTC-day high/low, valid only in the immediately next day and same data segment."""
    complete = {}
    for day, g in d.groupby(d.index.floor("D"), sort=True):
        expected = pd.date_range(day, periods=96, freq=BAR)
        if len(g) != 96 or not g.index.equals(expected) or g.segment.nunique() != 1:
            continue
        complete[day] = (
            float(g.high.max()), float(g.low.min()), int(g.segment.iloc[0])
        )
    rows = []
    for ts, current_segment in zip(d.index, d.segment.to_numpy()):
        previous_day = ts.floor("D") - DAY
        value = complete.get(previous_day)
        if value is None or value[2] != int(current_segment):
            rows.append((np.nan, np.nan))
        else:
            rows.append((value[0], value[1]))
    return pd.DataFrame(rows, index=d.index, columns=["resistance", "support"])

def confirmed_4h_pivot_levels(d, left=2, right=2):
    """Last confirmed 4H pivot high/low, available after right-side bars close."""
    h = complete_resample(d, "4h", 16, H4, "4h")
    records = {}
    last_resistance = np.nan
    last_support = np.nan
    active_bar_segment = None
    for i in range(left, len(h) - right):
        bar_segment = int(h.bar_segment.iloc[i])
        if active_bar_segment != bar_segment:
            last_resistance = np.nan
            last_support = np.nan
            active_bar_segment = bar_segment
        window = h.iloc[i-left:i+right+1]
        if window.source_segment.nunique() != 1 or window.bar_segment.nunique() != 1:
            continue
        high, low = float(h.high.iloc[i]), float(h.low.iloc[i])
        new_level = False
        if high > float(h.high.iloc[i-left:i].max()) and high > float(h.high.iloc[i+1:i+right+1].max()):
            last_resistance = high
            new_level = True
        if low < float(h.low.iloc[i-left:i].min()) and low < float(h.low.iloc[i+1:i+right+1].min()):
            last_support = low
            new_level = True
        if new_level:
            available = h.index[i + right]
            records[available] = {
                "resistance": last_resistance,
                "support": last_support,
                "source_segment": int(h.source_segment.iloc[i]),
            }
    if not records:
        return pd.DataFrame(index=d.index, columns=["resistance", "support"], dtype=float)
    levels = pd.DataFrame.from_dict(records, orient="index").sort_index()
    levels.index = pd.DatetimeIndex(levels.index)
    aligned = levels.reindex(d.index, method="ffill")
    # A confirmed level from a prior raw-data segment is not carried across a gap.
    same_segment = aligned.source_segment.eq(d.segment)
    aligned.loc[~same_segment, ["resistance", "support"]] = np.nan
    return aligned[["resistance", "support"]]

def build_features(raw):
    d = add_segments(validate_ohlc(raw))
    d["atr14"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        d.loc[g.index, "atr14"] = wilder_atr_segment(g).to_numpy()

    h = complete_resample(d, "1h", 4, H1, "1h")
    # Reset the EMA state after either a raw-data gap or an incomplete hour.
    h["ema50"] = h.groupby("bar_segment").close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    h["ema200"] = h.groupby("bar_segment").close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    hctx = h[["close", "ema50", "ema200", "source_segment"]].reindex(
        d.index, method="ffill"
    )
    same_segment = hctx.source_segment.eq(d.segment)
    hctx.loc[~same_segment, ["close", "ema50", "ema200"]] = np.nan
    d["h_close"] = hctx.close
    d["ema50_1h"] = hctx.ema50
    d["ema200_1h"] = hctx.ema200
    bull = (d.h_close > d.ema50_1h) & (d.ema50_1h > d.ema200_1h)
    bear = (d.h_close < d.ema50_1h) & (d.ema50_1h < d.ema200_1h)
    d["regime"] = np.select(
        [bull.fillna(False), bear.fillna(False)],
        ["bull", "bear"],
        default="mixed_or_unavailable",
    )
    pd_levels = prior_day_levels(d)
    piv_levels = confirmed_4h_pivot_levels(d)
    for prefix, levels in (("pd", pd_levels), ("p4", piv_levels)):
        d[f"{prefix}_resistance"] = levels.resistance
        d[f"{prefix}_support"] = levels.support
    return d


def build_events(d, source, approach, tolerance, confirmation):
    prefix = "pd" if source == "prior_day" else "p4"
    resistance = d[f"{prefix}_resistance"].to_numpy(float)
    support = d[f"{prefix}_support"].to_numpy(float)
    atr = d.atr14.to_numpy(float)
    op = d.open.to_numpy(float)
    hi = d.high.to_numpy(float)
    lo = d.low.to_numpy(float)
    cl = d.close.to_numpy(float)
    seg = d.segment.to_numpy()
    events = []
    for i in range(1, len(d) - 2):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if not np.isfinite([resistance[i], support[i]]).any():
            continue
        pad = tolerance * atr[i]
        short_signal = False
        long_signal = False
        if np.isfinite(resistance[i]):
            if approach == "sweep_reclaim":
                short_signal = hi[i] >= resistance[i] + pad and cl[i] < resistance[i]
            else:
                short_signal = (
                    resistance[i] - pad <= hi[i] <= resistance[i] + pad
                    and cl[i] < resistance[i]
                )
        if np.isfinite(support[i]):
            if approach == "sweep_reclaim":
                long_signal = lo[i] <= support[i] - pad and cl[i] > support[i]
            else:
                long_signal = (
                    support[i] - pad <= lo[i] <= support[i] + pad
                    and cl[i] > support[i]
                )
        # A single candle cannot create contradictory long and short events.
        if short_signal == long_signal:
            continue
        side = "short" if short_signal else "long"
        signal_extreme = float(hi[i] if side == "short" else lo[i])
        entry_i = i + 1
        confirmation_i = i
        if confirmation == "next_bar_break":
            confirmation_i = i + 1
            if seg[confirmation_i] != seg[i]:
                continue
            confirmed = (
                cl[confirmation_i] < lo[i]
                if side == "short"
                else cl[confirmation_i] > hi[i]
            )
            if not confirmed:
                continue
            entry_i = i + 2
        if entry_i >= len(d) or seg[entry_i] != seg[i]:
            continue
        events.append({
            "signal_i": i,
            "confirmation_i": confirmation_i,
            "entry_i": entry_i,
            "side": side,
            "extreme": signal_extreme,
            "atr_signal": float(atr[i]),
            "source": source,
            "approach": approach,
            "tolerance": tolerance,
            "confirmation": confirmation,
        })
    return events


def resolve_exit(side, open_price, high, low, stop, target):
    # Conservative OHLC resolution: stop first, adverse gap at opening price.
    if side == "long":
        if low <= stop:
            return min(open_price, stop), "SL"
        if high >= target:
            return target, "TP"
    else:
        if high >= stop:
            return max(open_price, stop), "SL"
        if low <= target:
            return target, "TP"
    return None, None


def in_session(ts, session):
    return session == "all" or 7 <= ts.hour < 19


def metrics(trades):
    if trades.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
            "max_losing_streak": 0, "positive_month_fraction": 0.0,
        }
    x = trades.sort_values("entry_time")
    r = x.net_R.astype(float)
    wins, losses = r[r > 0], r[r < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) else (
        float("inf") if len(wins) else 0.0
    )
    equity = np.r_[0.0, r.cumsum().to_numpy()]
    dd = equity[1:] - np.maximum.accumulate(equity)[1:]
    streak = maximum = 0
    for value in r:
        streak = streak + 1 if value < 0 else 0
        maximum = max(maximum, streak)
    monthly = x.assign(month=x.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {
        "trades": int(len(x)),
        "win_rate_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else 999.0,
        "net_R": round(float(r.sum()), 3),
        "avg_R": round(float(r.mean()), 4),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 3),
        "max_losing_streak": int(maximum),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3) if len(monthly) else 0.0,
    }


def simulate(d, events, cfg, start_i, end_i, cost_bps=PRIMARY_COST):
    op = d.open.to_numpy(float)
    hi = d.high.to_numpy(float)
    lo = d.low.to_numpy(float)
    cl = d.close.to_numpy(float)
    seg = d.segment.to_numpy()
    regime = d.regime.to_numpy()
    rows = []
    last_exit = start_i - 1
    for ev in events:
        si, ci, ei = ev["signal_i"], ev["confirmation_i"], ev["entry_i"]
        if si < start_i or ci < start_i or ei < start_i or ei >= end_i:
            continue
        if ei <= last_exit or ei + MAX_HOLD > end_i or ei + MAX_HOLD > len(d):
            continue
        if not np.all(seg[si:ei + MAX_HOLD] == seg[si]):
            continue
        side = ev["side"]
        if cfg["direction"] == "long_only" and side != "long":
            continue
        if cfg["direction"] == "short_only" and side != "short":
            continue
        if not in_session(d.index[ei], cfg["session"]):
            continue
        if cfg["filter"] == "ema50_200":
            if side == "long" and regime[ei] != "bull":
                continue
            if side == "short" and regime[ei] != "bear":
                continue

        entry = float(op[ei])
        pad = cfg["stop_buffer"] * ev["atr_signal"]
        stop = ev["extreme"] + pad if side == "short" else ev["extreme"] - pad
        risk = stop - entry if side == "short" else entry - stop
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry - cfg["target_r"] * risk if side == "short" else entry + cfg["target_r"] * risk
        exit_i = ei + MAX_HOLD - 1
        exit_price = float(cl[exit_i])
        outcome = "TIME"
        for j in range(ei, ei + MAX_HOLD):
            fill, reason = resolve_exit(
                side, float(op[j]), float(hi[j]), float(lo[j]), stop, target
            )
            if reason:
                exit_i, exit_price, outcome = j, float(fill), reason
                break
        gross = (entry - exit_price) / risk if side == "short" else (exit_price - entry) / risk
        cost_r = entry * (cost_bps / 10000.0) / risk
        rows.append({
            "signal_time": d.index[si],
            "confirmation_time": d.index[ci],
            "entry_time": d.index[ei],
            "exit_time": d.index[exit_i],
            "side": side,
            "level_source": cfg["level_source"],
            "approach": cfg["approach"],
            "tolerance_atr": cfg["tolerance_atr"],
            "confirmation": cfg["confirmation"],
            "stop_buffer_atr": cfg["stop_buffer"],
            "target_r": cfg["target_r"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "outcome": outcome,
            "gross_R": gross,
            "cost_R": cost_r,
            "net_R": gross - cost_r,
            "regime": regime[ei],
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def add_cost_sensitivity(out, label, split, trades):
    if trades.empty:
        return
    for bps in COSTS:
        t = trades.copy()
        # Recompute each trade's cost using its own initial risk.
        risk = np.where(
            t.side.eq("short"), t.stop.to_numpy(float) - t.entry.to_numpy(float),
            t.entry.to_numpy(float) - t.stop.to_numpy(float),
        )
        t["net_R"] = t.gross_R - t.entry.to_numpy(float) * (bps / 10000.0) / risk
        out.append({"candidate": label, "split": split, "cost_bps": bps, **metrics(t)})


def monthly_summary(trades):
    if trades.empty:
        return pd.DataFrame()
    x = trades.assign(month=trades.entry_time.dt.strftime("%Y-%m"))
    return x.groupby("month").agg(
        trades=("net_R", "size"),
        win_rate_pct=("net_R", lambda s: float((s > 0).mean() * 100)),
        net_R=("net_R", "sum"),
    ).reset_index()


def regime_summary(trades):
    if trades.empty:
        return pd.DataFrame()
    return trades.groupby("regime").agg(
        trades=("net_R", "size"),
        win_rate_pct=("net_R", lambda s: float((s > 0).mean() * 100)),
        net_R=("net_R", "sum"),
        avg_R=("net_R", "mean"),
    ).reset_index()


def run_matrix(d):
    n = len(d)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    bounds = {
        "train": (0, train_end),
        "validation": (train_end, val_end),
        "oos": (val_end, n),
    }
    event_cache = {}
    for source, approach, tol, confirmation in itertools.product(
        LEVEL_SOURCES, APPROACHES, TOLERANCES, CONFIRMATIONS
    ):
        event_cache[(source, approach, tol, confirmation)] = build_events(
            d, source, approach, tol, confirmation
        )

    matrix_rows = []
    config_lookup = {}
    configs = list(itertools.product(
        LEVEL_SOURCES, APPROACHES, TOLERANCES, CONFIRMATIONS,
        BUFFERS, TARGETS, FILTERS, DIRECTIONS, SESSIONS
    ))
    for values in configs:
        source, approach, tol, confirmation, buffer, target, filt, direction, session = values
        cid = (
            f"{source}_{approach}_tol{tol}_{confirmation}_buf{buffer}_"
            f"{target}R_{filt}_{direction}_{session}"
        )
        cfg = {
            "config_id": cid, "level_source": source, "approach": approach,
            "tolerance_atr": tol, "confirmation": confirmation,
            "stop_buffer": buffer, "target_r": target, "filter": filt,
            "direction": direction, "session": session,
        }
        config_lookup[cid] = cfg
        events = event_cache[(source, approach, tol, confirmation)]
        train = simulate(d, events, cfg, *bounds["train"])
        validation = simulate(d, events, cfg, *bounds["validation"])
        mt, mv = metrics(train), metrics(validation)
        matrix_rows.append({
            **cfg,
            **{f"train_{k}": v for k, v in mt.items()},
            **{f"validation_{k}": v for k, v in mv.items()},
        })

    matrix = pd.DataFrame(matrix_rows)
    matrix.to_csv(OUT / "matrix.csv", index=False)
    train_ok = (
        (matrix.train_trades >= MIN_TRAIN)
        & (matrix.train_net_R > 0)
        & (matrix.train_profit_factor >= 1.05)
        & (matrix.train_max_drawdown_R >= -25)
        & (matrix.train_positive_month_fraction >= 0.50)
    )
    eligible = matrix[train_ok].copy()
    if not eligible.empty:
        eligible["quality"] = eligible.train_net_R / eligible.train_max_drawdown_R.abs().clip(lower=1.0)
        shortlist = eligible.sort_values(["quality", "train_trades"], ascending=[False, False]).head(MAX_SHORTLIST)
        val_ok = (
            (shortlist.validation_trades >= MIN_VALIDATION)
            & (shortlist.validation_net_R > 0)
            & (shortlist.validation_profit_factor >= 1.05)
            & (shortlist.validation_max_drawdown_R >= -15)
            & (shortlist.validation_positive_month_fraction >= 0.50)
        )
        passed = shortlist[val_ok].copy()
    else:
        shortlist = pd.DataFrame()
        passed = pd.DataFrame()

    top_train = matrix[matrix.train_trades > 0].sort_values("train_net_R", ascending=False).head(10)
    top_val = matrix[matrix.validation_trades >= MIN_VALIDATION].sort_values(
        "validation_net_R", ascending=False
    ).head(10)
    top_train.to_csv(OUT / "top_train.csv", index=False)
    top_val.to_csv(OUT / "top_validation_min20.csv", index=False)

    sensitivity = []
    diagnostic_sets = {}
    for label, row in (
        ("best_train", top_train.iloc[0] if not top_train.empty else None),
        ("best_validation_min20", top_val.iloc[0] if not top_val.empty else None),
    ):
        if row is None:
            continue
        cfg = config_lookup[row.config_id]
        events = event_cache[(cfg["level_source"], cfg["approach"],
                              cfg["tolerance_atr"], cfg["confirmation"])]
        tr = simulate(d, events, cfg, *bounds["train"])
        va = simulate(d, events, cfg, *bounds["validation"])
        tr.to_csv(OUT / f"{label}_train_trades.csv", index=False)
        va.to_csv(OUT / f"{label}_validation_trades.csv", index=False)
        monthly_summary(tr).to_csv(OUT / f"{label}_train_monthly.csv", index=False)
        monthly_summary(va).to_csv(OUT / f"{label}_validation_monthly.csv", index=False)
        regime_summary(tr).to_csv(OUT / f"{label}_train_regimes.csv", index=False)
        regime_summary(va).to_csv(OUT / f"{label}_validation_regimes.csv", index=False)
        diagnostic_sets[label] = (tr, va)
        add_cost_sensitivity(sensitivity, label, "train", tr)
        add_cost_sensitivity(sensitivity, label, "validation", va)
    pd.DataFrame(sensitivity).to_csv(OUT / "cost_sensitivity.csv", index=False)

    oos_summary = {}
    if not passed.empty:
        passed = passed.copy()
        passed["validation_quality"] = passed.validation_net_R / passed.validation_max_drawdown_R.abs().clip(lower=1.0)
        selected = passed.sort_values(
            ["validation_quality", "validation_trades"], ascending=[False, False]
        ).iloc[0]
        cid = selected.config_id
        cfg = config_lookup[cid]
        events = event_cache[(cfg["level_source"], cfg["approach"],
                              cfg["tolerance_atr"], cfg["confirmation"])]
        oos = simulate(d, events, cfg, *bounds["oos"])
        oos.to_csv(OUT / "selected_oos_trades.csv", index=False)
        monthly_summary(oos).to_csv(OUT / "selected_oos_monthly.csv", index=False)
        regime_summary(oos).to_csv(OUT / "selected_oos_regimes.csv", index=False)
        oos_summary = metrics(oos)
    else:
        (OUT / "oos_not_evaluated.txt").write_text(
            "No configuration passed the preregistered train and validation gates; OOS not evaluated.\n"
        )

    metadata = {
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "rows": len(d),
        "start_utc": str(d.index.min()),
        "end_utc": str(d.index.max()),
        "gaps": int((d.index.to_series().diff().dropna() != BAR).sum()),
        "dataset_sha256": sha256(OUT / "BTCUSD_15m.csv"),
        "train_end_utc": str(d.index[train_end]),
        "validation_end_utc": str(d.index[val_end]),
        "oos_start_utc": str(d.index[val_end]),
        "configurations": len(matrix),
        "train_eligible": len(eligible),
        "shortlisted": len(shortlist),
        "validation_passes": len(passed),
        "oos_evaluated": bool(not passed.empty),
        "oos_summary": oos_summary,
        "primary_cost_bps": PRIMARY_COST,
        "cost_sensitivity_bps": list(COSTS),
        "cost_assumption": "assumed round-trip cost on one BTC leg; account fee tier, separate spread/market impact and funding unverified/excluded",
        "signal": "previous complete UTC-day high/low or last confirmed 4H pivot; 15m sweep-reclaim or near-level rejection; optional next-bar break confirmation",
        "execution": "next 15m open; structural stop beyond rejection wick plus 0/0.1 ATR14; 1.5/2/3R target; 8h maximum hold; one position/config; stop first on same-bar ambiguity; adverse gap stop at worse open",
        "causality": "daily levels available only during the immediately following UTC day and only within the same contiguous data segment; 4H pivots available only after right-side confirmation bars close and are masked across segment gaps; 1H EMA50/200 uses complete 1H bars and resets after incomplete-hour or raw-data gaps; ATR resets per contiguous 15m segment",
        "split": "chronological 70/15/15; train >=40 trades, PF>=1.05, positive net R, DD>=-25R and >=50% positive active months; validation >=20, PF>=1.05, positive net R, DD>=-15R and >=50% positive active months; OOS only after both gates",
        "limitations": ["Delta BTCUSD OHLC only; no order-book spread/market impact model.",
                        "Assumed fees, not account-tier verified; funding excluded for max 8h hold.",
                        "UTC session proxy 07-19 does not adjust for daylight saving.",
                        "Daily levels require a complete prior UTC day; incomplete days are not used.",
                        "Confirmed 4H pivots use two bars on each side and are available only after confirmation."],
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print("DATA", json.dumps({k: metadata[k] for k in (
        "rows", "start_utc", "end_utc", "gaps", "dataset_sha256",
        "train_end_utc", "validation_end_utc", "oos_start_utc")}, indent=2))
    print(f"CONFIGURATIONS: {len(matrix)}")
    print(f"TRAIN ELIGIBLE: {len(eligible)}; SHORTLIST: {len(shortlist)}; VALIDATION PASSES: {len(passed)}")
    print("TOP TRAIN")
    cols = ["config_id", "train_trades", "train_win_rate_pct", "train_profit_factor",
            "train_net_R", "train_max_drawdown_R", "train_max_losing_streak",
            "train_positive_month_fraction"]
    print(top_train[cols].head(5).to_string(index=False))
    print("TOP VALIDATION (minimum 20 trades)")
    cols = ["config_id", "validation_trades", "validation_win_rate_pct",
            "validation_profit_factor", "validation_net_R", "validation_max_drawdown_R",
            "validation_max_losing_streak", "validation_positive_month_fraction"]
    print(top_val[cols].head(5).to_string(index=False))
    if not passed.empty:
        print("OOS", json.dumps(oos_summary, indent=2))
    else:
        print("OOS NOT EVALUATED")


def self_test():
    # Prior-day levels: day one is unavailable during day one; day two sees day one.
    idx = pd.date_range("2025-01-01", periods=192, freq="15min", tz="UTC")
    close = np.full(len(idx), 100.0)
    raw = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1, "close": close
    }, index=idx)
    d = add_segments(raw)
    levels = prior_day_levels(d)
    assert pd.isna(levels.resistance.iloc[0])
    assert levels.resistance.iloc[96] == 101.0
    assert levels.support.iloc[96] == 99.0

    # An incomplete prior day and a segment break invalidate the prior-day level.
    gap_raw = raw.drop(index=raw.index[96])
    gap_d = add_segments(gap_raw)
    gap_levels = prior_day_levels(gap_d)
    assert gap_levels.resistance.isna().all()

    # Exercise the actual 4H pivot builder: high in bar 2 is confirmed at bar 4 close.
    block_high = [10, 11, 15, 12, 11, 10, 9]
    block_low = [5, 4, 6, 3, 5, 6, 7]
    pidx = pd.date_range("2025-01-01", periods=7 * 16, freq="15min", tz="UTC")
    po, ph, pl, pc = [], [], [], []
    for bh, bl in zip(block_high, block_low):
        po.extend([8.0] * 16)
        ph.extend([float(bh)] * 16)
        pl.extend([float(bl)] * 16)
        pc.extend([8.0] * 16)
    praw = pd.DataFrame({"open": po, "high": ph, "low": pl, "close": pc}, index=pidx)
    pd0 = add_segments(praw)
    piv = confirmed_4h_pivot_levels(pd0)
    available_i = 5 * 16
    assert pd.isna(piv.resistance.iloc[available_i - 1])
    assert piv.resistance.iloc[available_i] == 15.0
    # A later confirmed pivot low must not erase the still-active last pivot high.
    assert piv.resistance.iloc[96] == 15.0
    assert piv.support.iloc[96] == 3.0

    # A pivot from before a data gap is not carried into the next segment.
    pbroken = add_segments(praw.drop(index=praw.index[100]))
    piv_broken = confirmed_4h_pivot_levels(pbroken)
    after_gap_i = pbroken.index.get_loc(praw.index[101])
    assert pd.isna(piv_broken.resistance.iloc[after_gap_i])

    # Causal event generation: sweep/reclaim at bar 1 enters at bar 2 open.
    eidx = pd.date_range("2025-02-01", periods=4, freq="15min", tz="UTC")
    ed = pd.DataFrame({
        "open": [100, 100, 99, 98],
        "high": [101, 102, 100, 99],
        "low": [99, 98, 97, 96],
        "close": [100, 99, 97.5, 97],
        "segment": [1, 1, 1, 1],
        "atr14": [1.0, 1.0, 1.0, 1.0],
        "pd_resistance": [100.0] * 4,
        "pd_support": [90.0] * 4,
        "p4_resistance": [100.0] * 4,
        "p4_support": [90.0] * 4,
        "regime": ["bear"] * 4,
        "ema50_1h": [99.0] * 4,
        "ema200_1h": [98.0] * 4,
    }, index=eidx)
    ev = build_events(ed, "prior_day", "sweep_reclaim", 0.0, "signal_close")
    assert len(ev) == 1 and ev[0]["side"] == "short" and ev[0]["entry_i"] == 2
    ev_confirm = build_events(ed, "prior_day", "sweep_reclaim", 0.0, "next_bar_break")
    assert len(ev_confirm) == 1 and ev_confirm[0]["confirmation_i"] == 2 and ev_confirm[0]["entry_i"] == 3

    # If the next candle does not break the rejection low, confirmation is rejected.
    ed_bad = ed.copy()
    ed_bad.loc[eidx[2], "close"] = 99.5
    ev_bad = build_events(ed_bad, "prior_day", "sweep_reclaim", 0.0, "next_bar_break")
    assert len(ev_bad) == 0

    # Conservative stop-first ambiguity and adverse stop gap; target fill at target.
    assert resolve_exit("long", 100, 120, 80, 90, 110) == (90, "SL")
    assert resolve_exit("short", 85, 120, 80, 110, 90) == (110, "SL")
    assert resolve_exit("long", 85, 95, 80, 90, 110) == (85, "SL")
    assert resolve_exit("short", 100, 105, 85, 110, 90) == (90, "TP")

    print("13 support/resistance causality and execution tests passed")

def main():
    import sys
    if "--self-test" in sys.argv:
        self_test()
        return
    raw = fetch("15m")
    d = build_features(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m data: {len(d)}")
    data_path = OUT / "BTCUSD_15m.csv"
    d.to_csv(data_path)
    run_matrix(d)


if __name__ == "__main__":
    main()
