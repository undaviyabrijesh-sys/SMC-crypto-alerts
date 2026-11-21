"""BTCUSD 15m confirmed-liquidity sweep + local MSS reversal research.

External liquidity = confirmed 1H swing high/low (2 or 3 bars each side).
A sweep requires wick-through and close-back-across the frozen level.
MSS requires a later 15m close through the last pre-sweep confirmed local swing.
Entry is next 15m open. All pivots are used only after right-side confirmation.
Research-only; no live signals or execution.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("liquidity_mss_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD = 32
LEVEL_MAX_AGE = 288  # 72h after the 1H pivot is confirmed
COSTS = (6, 12, 20)
EXTERNAL_STRENGTHS = (2, 3)
LOCAL_STRENGTHS = (2, 3)
MSS_WAITS = (4, 8)
STOP_BUFFERS = (0.0, 0.1)
TARGETS = (1.5, 2.0, 3.0, 4.0)
HTF_FILTERS = ("none", "ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN = 40
MIN_VALIDATION = 20
MAX_SHORTLIST = 25


def wilder_atr(g, length=14):
    prev = g.close.shift(1)
    tr = pd.concat(
        [g.high - g.low, (g.high - prev).abs(), (g.low - prev).abs()],
        axis=1,
    ).max(axis=1)
    vals = tr.to_numpy(float)
    out = np.full(len(vals), np.nan)
    if len(vals) >= length and np.isfinite(vals[:length]).all():
        out[length - 1] = vals[:length].mean()
        for k in range(length, len(vals)):
            out[k] = (out[k - 1] * (length - 1) + vals[k]) / length
    return pd.Series(out, index=g.index)


def complete_resample(d, rule, expected):
    z = d[["open", "high", "low", "close"]].resample(
        rule, label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample(rule, label="right", closed="left").count()
    seg_counts = d.segment.resample(rule, label="right", closed="left").nunique()
    return z.loc[counts.eq(expected) & seg_counts.eq(1)].dropna()


def prepare(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d[(d.high >= d[["open", "close", "low"]].max(axis=1)) &
          (d.low <= d[["open", "close", "high"]].min(axis=1))]
    d["segment"] = d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    d["atr14"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        d.loc[g.index, "atr14"] = wilder_atr(g).to_numpy()

    h1 = complete_resample(d, "1h", 4)
    h1["segment"] = h1.index.to_series().diff().ne(pd.Timedelta("1h")).cumsum()
    h4 = complete_resample(d, "4h", 16)
    h4["segment"] = h4.index.to_series().diff().ne(pd.Timedelta("4h")).cumsum()
    for c in ("close",):
        h4[f"ema50_{c}"] = h4.groupby("segment")[c].transform(
            lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
        )
        h4[f"ema200_{c}"] = h4.groupby("segment")[c].transform(
            lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
        )
    for c in ("close", "ema50_close", "ema200_close"):
        d[f"h4_{c}"] = h4[c].reindex(d.index, method="ffill")
    bull = (d.h4_close > d.h4_ema50_close) & (d.h4_ema50_close > d.h4_ema200_close)
    bear = (d.h4_close < d.h4_ema50_close) & (d.h4_ema50_close < d.h4_ema200_close)
    d["regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )
    return d, h1


def confirmed_external_levels(d, h1, strength):
    """Return 1H pivot levels only at the close of their right-side confirmation bar."""
    hi = h1.high.to_numpy(float)
    lo = h1.low.to_numpy(float)
    seg = h1.segment.to_numpy()
    out = []
    n = len(h1)
    for p in range(strength, n - strength):
        window_seg = seg[p - strength:p + strength + 1]
        if not np.all(window_seg == window_seg[0]):
            continue
        left_hi = hi[p - strength:p]
        right_hi = hi[p + 1:p + strength + 1]
        left_lo = lo[p - strength:p]
        right_lo = lo[p + 1:p + strength + 1]
        available_at = h1.index[p + strength]
        ai = d.index.searchsorted(available_at, side="left")
        if ai >= len(d):
            continue
        if hi[p] > np.max(left_hi) and hi[p] >= np.max(right_hi):
            out.append((ai, "high", float(hi[p]), h1.index[p]))
        if lo[p] < np.min(left_lo) and lo[p] <= np.min(right_lo):
            out.append((ai, "low", float(lo[p]), h1.index[p]))
    return sorted(out, key=lambda x: (x[0], x[1]))


def confirmed_local_swings(d, strength):
    """At each 15m index, expose only pivots whose right bars have already closed."""
    hi = d.high.to_numpy(float)
    lo = d.low.to_numpy(float)
    seg = d.segment.to_numpy()
    n = len(d)
    hi_event = np.full(n, np.nan)
    lo_event = np.full(n, np.nan)
    for p in range(strength, n - strength):
        if not np.all(seg[p - strength:p + strength + 1] == seg[p]):
            continue
        if hi[p] > np.max(hi[p - strength:p]) and hi[p] >= np.max(hi[p + 1:p + strength + 1]):
            hi_event[p + strength] = hi[p]
        if lo[p] < np.min(lo[p - strength:p]) and lo[p] <= np.min(lo[p + 1:p + strength + 1]):
            lo_event[p + strength] = lo[p]
    last_hi = np.full(n, np.nan)
    last_lo = np.full(n, np.nan)
    cur_hi = np.nan
    cur_lo = np.nan
    for i in range(n):
        if np.isfinite(hi_event[i]):
            cur_hi = hi_event[i]
        if np.isfinite(lo_event[i]):
            cur_lo = lo_event[i]
        last_hi[i] = cur_hi
        last_lo[i] = cur_lo
    return last_hi, last_lo


def build_events(d, h1, external_strength, local_strength, mss_wait):
    levels = confirmed_external_levels(d, h1, external_strength)
    last_hi, last_lo = confirmed_local_swings(d, local_strength)
    op = d.open.to_numpy(float)
    cl = d.close.to_numpy(float)
    bh = d.high.to_numpy(float)
    bl = d.low.to_numpy(float)
    atr = d.atr14.to_numpy(float)
    seg = d.segment.to_numpy()
    events = []

    for available_i, level_side, level, pivot_time in levels:
        if available_i >= len(d) - 2:
            continue
        base_segment = seg[available_i]
        end = min(len(d) - 1, available_i + LEVEL_MAX_AGE)
        for k in range(available_i, end):
            if seg[k] != base_segment or not np.isfinite(atr[k]):
                break
            # The structure reference must have been confirmed before the sweep candle.
            prior_i = k - 1
            if prior_i < 0:
                continue
            if level_side == "high":
                swept = bh[k] > level and cl[k] < level
                invalidated = cl[k] > level
                side = "short"
                structure = last_lo[prior_i]
                extreme = bh[k]
            else:
                swept = bl[k] < level and cl[k] > level
                invalidated = cl[k] < level
                side = "long"
                structure = last_hi[prior_i]
                extreme = bl[k]

            if swept:
                if not np.isfinite(structure):
                    break
                mss_found = False
                for j in range(k + 1, min(k + mss_wait + 1, len(d) - 1)):
                    if seg[j] != base_segment:
                        break
                    if level_side == "high":
                        extreme = max(extreme, bh[j])
                        if cl[j] > level:  # reclaim failed; old high was accepted
                            break
                        mss = cl[j] < structure
                    else:
                        extreme = min(extreme, bl[j])
                        if cl[j] < level:
                            break
                        mss = cl[j] > structure
                    if mss:
                        entry_i = j + 1
                        if entry_i < len(d) and seg[entry_i] == base_segment:
                            events.append({
                                "pivot_time": pivot_time,
                                "available_i": available_i,
                                "sweep_i": k,
                                "mss_i": j,
                                "entry_i": entry_i,
                                "side": side,
                                "external_level": level,
                                "structure_level": float(structure),
                                "extreme": float(extreme),
                                "atr_sweep": float(atr[k]),
                                "external_strength": external_strength,
                                "local_strength": local_strength,
                                "mss_wait": mss_wait,
                            })
                        mss_found = True
                        break
                # One sweep attempt per confirmed external level.
                break
            if invalidated:
                break

    return sorted(events, key=lambda e: (e["entry_i"], e["sweep_i"]))


def trade_metrics(g, bps):
    if g.empty:
        return dict(
            trades=0, win_rate_pct=0.0, profit_factor=None, net_R=0.0,
            avg_R=0.0, max_drawdown_R=0.0, max_losing_streak=0,
            positive_month_fraction=0.0, TP=0, SL=0, TIME=0,
        )
    x = g.sort_values("entry_time")
    r = x[f"net_R_{bps}bp"].astype(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = r.cumsum().to_numpy()
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]
    streak = maximum = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        maximum = max(maximum, streak)
    monthly = x.assign(month=x.entry_time.dt.strftime("%Y-%m")).groupby("month")[
        f"net_R_{bps}bp"
    ].sum()
    return dict(
        trades=int(len(x)),
        win_rate_pct=round(float((r > 0).mean() * 100), 2),
        profit_factor=round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and abs(losses.sum()) else None,
        net_R=round(float(r.sum()), 2),
        avg_R=round(float(r.mean()), 3),
        max_drawdown_R=round(float(min(0.0, dd.min())), 2),
        max_losing_streak=int(maximum),
        positive_month_fraction=round(float((monthly > 0).mean()), 3)
        if len(monthly) else 0.0,
        TP=int((x.outcome == "TP").sum()),
        SL=int((x.outcome == "SL").sum()),
        TIME=int((x.outcome == "TIME").sum()),
    )


def simulate(d, events, cfg, start_i, end_i):
    op = d.open.to_numpy(float)
    hi = d.high.to_numpy(float)
    lo = d.low.to_numpy(float)
    cl = d.close.to_numpy(float)
    seg = d.segment.to_numpy()
    h4c = d.h4_close.to_numpy(float)
    h4e50 = d.h4_ema50_close.to_numpy(float)
    h4e200 = d.h4_ema200_close.to_numpy(float)
    regime = d.regime.to_numpy()
    rows = []
    last_exit = start_i - 1

    for ev in events:
        si, mi, ei = ev["sweep_i"], ev["mss_i"], ev["entry_i"]
        if si < start_i or mi < start_i or ei >= end_i or ei <= last_exit:
            continue
        side = ev["side"]
        if cfg["direction"] == "long_only" and side != "long":
            continue
        if cfg["direction"] == "short_only" and side != "short":
            continue
        entry_time = d.index[ei]
        if cfg["session"] == "07-19" and not (7 <= entry_time.hour < 19):
            continue
        if cfg["htf_filter"] == "ema50_200":
            if not np.isfinite([h4c[ei], h4e50[ei], h4e200[ei]]).all():
                continue
            aligned = (
                side == "long" and h4c[ei] > h4e50[ei] > h4e200[ei]
            ) or (
                side == "short" and h4c[ei] < h4e50[ei] < h4e200[ei]
            )
            if not aligned:
                continue

        end_trade = ei + MAX_HOLD
        if end_trade > end_i or end_trade > len(d):
            continue
        if not np.all(seg[ei:end_trade] == seg[ei]):
            continue

        entry = float(op[ei])
        buffer = cfg["stop_buffer"] * float(ev["atr_sweep"])
        stop = (
            float(ev["extreme"]) + buffer if side == "short"
            else float(ev["extreme"]) - buffer
        )
        risk = stop - entry if side == "short" else entry - stop
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry + cfg["target_r"] * risk if side == "long" else entry - cfg["target_r"] * risk

        outcome = "TIME"
        exit_i = end_trade - 1
        exit_price = float(cl[exit_i])
        for k in range(ei, end_trade):
            # Conservative gap handling and stop-first OHLC ambiguity.
            if side == "long":
                if op[k] <= stop:
                    outcome, exit_price, exit_i = "SL", float(op[k]), k
                    break
                if lo[k] <= stop:
                    outcome, exit_price, exit_i = "SL", stop, k
                    break
                if hi[k] >= target:
                    outcome, exit_price, exit_i = "TP", target, k
                    break
            else:
                if op[k] >= stop:
                    outcome, exit_price, exit_i = "SL", float(op[k]), k
                    break
                if hi[k] >= stop:
                    outcome, exit_price, exit_i = "SL", stop, k
                    break
                if lo[k] <= target:
                    outcome, exit_price, exit_i = "TP", target, k
                    break

        gross = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        row = {
            "config_id": cfg["config_id"],
            "external_strength": cfg["external_strength"],
            "local_strength": cfg["local_strength"],
            "mss_wait": cfg["mss_wait"],
            "stop_buffer": cfg["stop_buffer"],
            "target_r": cfg["target_r"],
            "htf_filter": cfg["htf_filter"],
            "direction": cfg["direction"],
            "session": cfg["session"],
            "sample": cfg["sample"],
            "side": side,
            "pivot_time": ev["pivot_time"],
            "sweep_time": d.index[si],
            "mss_time": d.index[mi],
            "entry_time": entry_time,
            "exit_time": d.index[exit_i],
            "external_level": ev["external_level"],
            "structure_level": ev["structure_level"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "outcome": outcome,
            "gross_R": gross,
            "regime": regime[ei],
        }
        for bps in COSTS:
            cost_r = (bps / 10000.0) * entry / risk
            row[f"cost_R_{bps}bp"] = cost_r
            row[f"net_R_{bps}bp"] = gross - cost_r
        rows.append(row)
        last_exit = exit_i
    return rows


def main():
    raw = fetch("15m")
    d, h1 = prepare(raw)
    if len(d) < 10000 or len(h1) < 1000:
        raise RuntimeError(f"Insufficient data: 15m={len(d)}, 1h={len(h1)}")
    gaps = int((d.index.to_series().diff().dropna() != BAR).sum())
    n = len(d)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    samples = (("train", 0, train_end), ("validation", train_end, val_end))
    dataset_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    event_cache = {}
    for ext_s, loc_s, wait in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS
    ):
        event_cache[(ext_s, loc_s, wait)] = build_events(d, h1, ext_s, loc_s, wait)

    configs = []
    for values in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS, STOP_BUFFERS,
        TARGETS, HTF_FILTERS, DIRECTIONS, SESSIONS
    ):
        ext_s, loc_s, wait, sb, target, htf, direction, session = values
        cfg_id = (
            f"h1p{ext_s}_mss{loc_s}_wait{wait}_buf{sb}_{target}R_"
            f"{htf}_{direction}_{session}"
        )
        configs.append(dict(
            config_id=cfg_id, external_strength=ext_s, local_strength=loc_s,
            mss_wait=wait, stop_buffer=sb, target_r=target,
            htf_filter=htf, direction=direction, session=session,
        ))

    trade_rows, summary_rows, monthly_rows, regime_rows = [], [], [], []
    for cfg in configs:
        events = event_cache[(cfg["external_strength"], cfg["local_strength"], cfg["mss_wait"])]
        for sample, start, end in samples:
            local = dict(cfg, sample=sample)
            rows = simulate(d, events, local, start, end)
            if rows:
                trade_rows.extend(rows)
            g = pd.DataFrame(rows)
            for bps in COSTS:
                summary_rows.append(dict(**local, cost_bps=bps, **trade_metrics(g, bps)))
            if not g.empty:
                x = g.copy()
                x["month"] = x.entry_time.dt.strftime("%Y-%m")
                for month in x.month.unique():
                    q = x[x.month == month]
                    for bps in COSTS:
                        monthly_rows.append(dict(
                            config_id=cfg["config_id"], sample=sample,
                            month=month, cost_bps=bps, trades=len(q),
                            net_R=round(float(q[f"net_R_{bps}bp"].sum()), 2),
                        ))
                for reg in x.regime.unique():
                    q = x[x.regime == reg]
                    for bps in COSTS:
                        regime_rows.append(dict(
                            config_id=cfg["config_id"], sample=sample,
                            regime=reg, cost_bps=bps, trades=len(q),
                            net_R=round(float(q[f"net_R_{bps}bp"].sum()), 2),
                        ))

    summary = pd.DataFrame(summary_rows)
    trades = pd.DataFrame(trade_rows)
    summary.to_csv(OUT / "summary.csv", index=False)
    trades.to_csv(OUT / "trades.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(OUT / "monthly_summary.csv", index=False)
    pd.DataFrame(regime_rows).to_csv(OUT / "regime_summary.csv", index=False)

    primary = summary[summary.cost_bps == 12]
    tr = primary[primary["sample"] == "train"].copy()
    va = primary[primary["sample"] == "validation"].copy()
    eligible = tr[
        (tr.trades >= MIN_TRAIN) & (tr.net_R > 0) &
        (tr.profit_factor >= 1.05) & (tr.max_drawdown_R >= -25)
    ].copy()
    eligible["selection_score"] = eligible.net_R / (eligible.max_drawdown_R.abs() + 1)
    shortlist = eligible.sort_values("selection_score", ascending=False).head(MAX_SHORTLIST)
    passed = []
    for _, candidate in shortlist.iterrows():
        v = va[va.config_id == candidate.config_id]
        if v.empty:
            continue
        v = v.iloc[0]
        if (
            v.trades >= MIN_VALIDATION and v.net_R > 0 and
            pd.notna(v.profit_factor) and v.profit_factor >= 1.05 and
            v.max_drawdown_R >= -15 and v.positive_month_fraction >= 0.50
        ):
            passed.append((candidate, v))

    selected = None
    oos_note = "OOS NOT EVALUATED: no candidate passed the pre-registered train/validation gates."
    if passed:
        selected = max(
            passed,
            key=lambda pair: pair[1].net_R / (abs(pair[1].max_drawdown_R) + 1)
        )[0]
        oos_cfg = dict(selected[[
            "config_id", "external_strength", "local_strength", "mss_wait",
            "stop_buffer", "target_r", "htf_filter", "direction", "session"
        ]].to_dict(), sample="oos")
        oos_events = event_cache[(
            oos_cfg["external_strength"], oos_cfg["local_strength"], oos_cfg["mss_wait"]
        )]
        oos_rows = simulate(d, oos_events, oos_cfg, val_end, n)
        if oos_rows:
            trades = pd.concat([trades, pd.DataFrame(oos_rows)], ignore_index=True)
            pd.DataFrame(oos_rows).to_csv(OUT / "selected_oos_trades.csv", index=False)
            oos_metrics = trade_metrics(pd.DataFrame(oos_rows), 12)
            oos_note = "One pre-selected validation-passing candidate evaluated once on OOS. " + json.dumps(oos_metrics)
        else:
            oos_note = "A candidate passed selection, but no eligible OOS trades were generated."
        trades.to_csv(OUT / "trades.csv", index=False)

    metadata = {
        "symbol": "BTCUSD",
        "timeframe": "15m execution; 1h confirmed external swing levels; completed 4h EMA regime",
        "rows_15m": len(d),
        "rows_1h_complete": len(h1),
        "start_utc": str(d.index.min()),
        "end_utc": str(d.index.max()),
        "gaps_15m": gaps,
        "dataset_sha256": dataset_hash,
        "train_end_utc": str(d.index[train_end - 1]),
        "validation_end_utc": str(d.index[val_end - 1]),
        "oos_start_utc": str(d.index[val_end]),
        "matrix_configurations": len(configs),
        "event_cache_counts": {str(k): len(v) for k, v in event_cache.items()},
        "train_eligible": len(eligible),
        "shortlisted": len(shortlist),
        "validation_pass": len(passed),
        "selected_oos_config": None if selected is None else selected.config_id,
        "oos_evaluated": bool(passed),
        "cost_sensitivity_bps": list(COSTS),
        "cost_assumption": "6/12/20bp round-trip; no funding or separate spread/slippage",
        "execution": "confirmed 1h pivot high/low becomes available only after right-side confirmation; 15m wick sweeps and closes back across frozen level; later 15m close breaks last pre-sweep confirmed opposite local swing; next 15m open entry; stop beyond full sweep-to-MSS excursion plus 0/0.1 ATR; fixed 1.5/2/3/4R target; 8h max hold; stop-first OHLC ambiguity; adverse gap-through stop fill",
        "split": "chronological 70/15/15; training eligibility then top-25 shortlist then validation; untouched OOS evaluated once only if one candidate passes both gates",
        "selection": {
            "train": ">=40 trades, net_R>0, PF>=1.05, max DD no worse than -25R",
            "validation": ">=20 trades, net_R>0, PF>=1.05, max DD no worse than -15R, >=50% positive active months",
            "shortlist": "top 25 by train net_R/(abs(max_drawdown_R)+1)"
        },
        "limitations": "12bp primary cost assumed, not user fee-tier verified; 6/20bp sensitivity only; no funding or separate spread/slippage; 07-19 UTC is a fixed session proxy; pivots use strict-left/non-strict-right tie handling; one trade at a time per configuration; external level age capped at 72h; mechanical pivot/MSS definitions are not discretionary SMC",
    }
    (OUT / "methodology.json").write_text(json.dumps(metadata, indent=2))
    (OUT / "oos_status.txt").write_text(oos_note)

    print("METHODOLOGY")
    print(json.dumps(metadata, indent=2))
    print("\nTOP TRAIN (12bp, nonzero trades)")
    print(tr[tr.trades > 0].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print("\nTOP VALIDATION (12bp, nonzero trades)")
    print(va[va.trades > 0].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)} SHORTLIST={len(shortlist)} VALIDATION PASS={len(passed)}")
    print(oos_note)
    print(f"Artifacts: {OUT}/summary.csv, trades.csv, monthly_summary.csv, regime_summary.csv, methodology.json")


if __name__ == "__main__":
    main()
