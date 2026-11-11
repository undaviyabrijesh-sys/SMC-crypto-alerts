"""BTCUSD liquidity-sweep + MSS + fair-value-gap retracement research.

A confirmed 1H swing is swept and reclaimed; a confirmed 15m MSS must occur;
the MSS candle must form a same-direction 3-candle FVG and meet a directional
body/displacement threshold. After the MSS close, a limit order is placed
inside the FVG. No entry is assumed on the signal candle.

Research only. No live signals, orders, or execution alerts.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import liquidity_sweep_mss_displacement_intraday_backtest as disp
base = disp.base

OUT = Path("liquidity_fvg_retrace_results")
OUT.mkdir(exist_ok=True)

COSTS = (6, 12, 20)
EXTERNAL_STRENGTHS = (3,)
LOCAL_STRENGTHS = (3,)
MSS_WAITS = (8,)
DISPLACEMENT_MODES = (
    ("body_0.5_atr_close_quartile", 0.5, True),
    ("body_0.75_atr_close_quartile", 0.75, True),
)
ENTRY_DEPTHS = (0.50, 0.75)
STOP_BUFFERS = (0.0, 0.1)
TARGETS = (1.5, 2.0, 3.0)
HTF_FILTERS = ("none", "ema50_200")
MAX_PENDING = 8       # 2 hours to fill after the MSS close
MAX_HOLD = 32         # 8 hours after fill
MIN_TRAIN = 40
MIN_VALIDATION = 20
MAX_SHORTLIST = 10


def make_fvg_event(d, event, mode):
    i = int(event["mss_i"])
    if i < 2 or d.segment.iloc[i] != d.segment.iloc[i - 2]:
        return None
    if not disp.displacement_ok(d, event, mode):
        return None

    side = event["side"]
    hi2 = float(d.high.iloc[i - 2])
    lo2 = float(d.low.iloc[i - 2])
    hi = float(d.high.iloc[i])
    lo = float(d.low.iloc[i])

    if side == "long" and lo > hi2:
        bottom, top = hi2, lo
    elif side == "short" and hi < lo2:
        bottom, top = hi, lo2
    else:
        return None

    width = top - bottom
    atr = float(d.atr14.iloc[i])
    if not np.isfinite([bottom, top, width, atr]).all() or width <= 0 or atr <= 0:
        return None
    out = dict(event)
    out["fvg_bottom"] = bottom
    out["fvg_top"] = top
    out["fvg_width"] = width
    out["mss_atr"] = atr
    return out


def metrics(g, bps):
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
    peaks = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    dd = eq - peaks
    streak = maximum = 0
    for value in r:
        streak = streak + 1 if value < 0 else 0
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
    last_busy = start_i - 1
    for ev in events:
        si, mi = int(ev["sweep_i"]), int(ev["mss_i"])
        if si < start_i or mi < start_i or mi <= last_busy:
            continue
        if mi + 1 >= end_i:
            continue

        side = ev["side"]
        buffer = cfg["stop_buffer"] * float(ev["atr_sweep"])
        stop = (
            float(ev["extreme"]) - buffer if side == "long"
            else float(ev["extreme"]) + buffer
        )
        depth = cfg["entry_depth"]
        width = float(ev["fvg_width"])
        limit = (
            float(ev["fvg_top"]) - depth * width if side == "long"
            else float(ev["fvg_bottom"]) + depth * width
        )
        if side == "long" and not stop < limit:
            continue
        if side == "short" and not stop > limit:
            continue
        if abs(limit - stop) / max(abs(limit), 1e-12) > 0.05:
            continue

        pending_end = min(end_i, mi + 1 + MAX_PENDING)
        fill_i = None
        entry = None
        fill_at_open = False
        for k in range(mi + 1, pending_end):
            if seg[k] != seg[mi]:
                break
            # A gap through the protective stop invalidates an unfilled order.
            if side == "long":
                if op[k] <= stop:
                    break
                if op[k] <= limit:
                    candidate = float(op[k])
                    candidate_at_open = True
                elif lo[k] <= limit:
                    candidate = limit
                    candidate_at_open = False
                else:
                    candidate = None
                if candidate is not None:
                    risk_check = candidate - stop
                    if risk_check <= 0 or risk_check / candidate > 0.05:
                        break
                    fill_i, entry, fill_at_open = k, candidate, candidate_at_open
                    break
                if cl[k] < float(ev["external_level"]):
                    break
            else:
                if op[k] >= stop:
                    break
                if op[k] >= limit:
                    candidate = float(op[k])
                    candidate_at_open = True
                elif hi[k] >= limit:
                    candidate = limit
                    candidate_at_open = False
                else:
                    candidate = None
                if candidate is not None:
                    risk_check = stop - candidate
                    if risk_check <= 0 or risk_check / candidate > 0.05:
                        break
                    fill_i, entry, fill_at_open = k, candidate, candidate_at_open
                    break
                if cl[k] > float(ev["external_level"]):
                    break

        if fill_i is None:
            last_busy = max(last_busy, pending_end - 1)
            continue
        # Require the complete maximum holding window to remain inside the sample.
        trade_end = fill_i + MAX_HOLD
        if trade_end > end_i or not np.all(seg[fill_i:trade_end] == seg[fill_i]):
            last_busy = max(last_busy, fill_i)
            continue

        if cfg["htf_filter"] == "ema50_200":
            if not np.isfinite([h4c[fill_i], h4e50[fill_i], h4e200[fill_i]]).all():
                last_busy = max(last_busy, fill_i)
                continue
            aligned = (
                side == "long" and h4c[fill_i] > h4e50[fill_i] > h4e200[fill_i]
            ) or (
                side == "short" and h4c[fill_i] < h4e50[fill_i] < h4e200[fill_i]
            )
            if not aligned:
                last_busy = max(last_busy, fill_i)
                continue

        risk = entry - stop if side == "long" else stop - entry
        if risk <= 0 or risk / entry > 0.05:
            last_busy = max(last_busy, fill_i)
            continue
        target = (
            entry + cfg["target_r"] * risk if side == "long"
            else entry - cfg["target_r"] * risk
        )

        outcome = "TIME"
        exit_i = trade_end - 1
        exit_price = float(cl[exit_i])
        for k in range(fill_i, trade_end):
            # A touch-filled limit and target on the same OHLC bar have unknown order.
            # Give no TP credit on that fill bar; still honour a stop touch.
            if k == fill_i and not fill_at_open:
                if side == "long" and lo[k] <= stop:
                    outcome, exit_price, exit_i = "SL", stop, k
                    break
                if side == "short" and hi[k] >= stop:
                    outcome, exit_price, exit_i = "SL", stop, k
                    break
                continue
            # Gap exits first; then stop before target for ambiguous OHLC candles.
            if side == "long":
                if op[k] <= stop:
                    outcome, exit_price, exit_i = "SL", float(op[k]), k
                    break
                if op[k] >= target:
                    outcome, exit_price, exit_i = "TP", float(op[k]), k
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
                if op[k] <= target:
                    outcome, exit_price, exit_i = "TP", float(op[k]), k
                    break
                if hi[k] >= stop:
                    outcome, exit_price, exit_i = "SL", stop, k
                    break
                if lo[k] <= target:
                    outcome, exit_price, exit_i = "TP", target, k
                    break

        gross = (
            (exit_price - entry) / risk if side == "long"
            else (entry - exit_price) / risk
        )
        row = {
            "config_id": cfg["config_id"],
            "external_strength": cfg["external_strength"],
            "local_strength": cfg["local_strength"],
            "mss_wait": cfg["mss_wait"],
            "displacement_mode": cfg["displacement_mode"],
            "entry_depth": cfg["entry_depth"],
            "stop_buffer": cfg["stop_buffer"],
            "target_r": cfg["target_r"],
            "htf_filter": cfg["htf_filter"],
            "sample": cfg["sample"],
            "side": side,
            "pivot_time": ev["pivot_time"],
            "sweep_time": d.index[si],
            "mss_time": d.index[mi],
            "entry_time": d.index[fill_i],
            "fill_type": "at_open" if fill_at_open else "intrabar_touch",
            "exit_time": d.index[exit_i],
            "fvg_bottom": ev["fvg_bottom"],
            "fvg_top": ev["fvg_top"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "outcome": outcome,
            "gross_R": gross,
            "regime": regime[fill_i],
        }
        for bps in COSTS:
            cost_r = (bps / 10000.0) * entry / risk
            row[f"cost_R_{bps}bp"] = cost_r
            row[f"net_R_{bps}bp"] = gross - cost_r
        rows.append(row)
        last_busy = exit_i
    return rows


def main():
    raw = base.fetch("15m")
    d, h1 = base.prepare(raw)
    if len(d) < 10000 or len(h1) < 1000:
        raise RuntimeError(f"Insufficient data: 15m={len(d)}, 1h={len(h1)}")
    n = len(d)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    samples = (("train", 0, train_end), ("validation", train_end, val_end))
    gaps = int((d.index.to_series().diff().dropna() != base.BAR).sum())
    dataset_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    event_cache = {}
    mode_map = {x[0]: x for x in DISPLACEMENT_MODES}
    event_counts = {}
    for ext_s, loc_s, wait in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS
    ):
        raw_events = base.build_events(d, h1, ext_s, loc_s, wait)
        for mode_name, mode in mode_map.items():
            key = (ext_s, loc_s, wait, mode_name)
            filtered = []
            for event in raw_events:
                fvg_event = make_fvg_event(d, event, mode)
                if fvg_event is not None:
                    filtered.append(fvg_event)
            event_cache[key] = filtered
            event_counts[mode_name] = event_counts.get(mode_name, 0) + len(filtered)

    configs = []
    for values in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS,
        DISPLACEMENT_MODES, ENTRY_DEPTHS, STOP_BUFFERS, TARGETS, HTF_FILTERS
    ):
        ext_s, loc_s, wait, mode, depth, sb, target, htf = values
        mode_name = mode[0]
        cfg_id = (
            f"h1p{ext_s}_mss{loc_s}_wait{wait}_{mode_name}_"
            f"fvg{depth}_buf{sb}_{target}R_{htf}"
        )
        configs.append(dict(
            config_id=cfg_id, external_strength=ext_s, local_strength=loc_s,
            mss_wait=wait, displacement_mode=mode_name, entry_depth=depth,
            stop_buffer=sb, target_r=target, htf_filter=htf,
        ))

    trade_rows, summary_rows, monthly_rows, regime_rows = [], [], [], []
    for cfg in configs:
        events = event_cache[(
            cfg["external_strength"], cfg["local_strength"], cfg["mss_wait"],
            cfg["displacement_mode"]
        )]
        for sample, start, end in samples:
            local = dict(cfg, sample=sample)
            rows = simulate(d, events, local, start, end)
            trade_rows.extend(rows)
            g = pd.DataFrame(rows)
            for bps in COSTS:
                summary_rows.append(dict(**local, cost_bps=bps, **metrics(g, bps)))
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
                for regime_name in x.regime.unique():
                    q = x[x.regime == regime_name]
                    for bps in COSTS:
                        regime_rows.append(dict(
                            config_id=cfg["config_id"], sample=sample,
                            regime=regime_name, cost_bps=bps, trades=len(q),
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
        (tr.profit_factor >= 1.05) & (tr.max_drawdown_R >= -25) &
        (tr.positive_month_fraction >= 0.50)
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
            "displacement_mode", "entry_depth", "stop_buffer", "target_r", "htf_filter"
        ]].to_dict(), sample="oos")
        oos_events = event_cache[(
            oos_cfg["external_strength"], oos_cfg["local_strength"],
            oos_cfg["mss_wait"], oos_cfg["displacement_mode"]
        )]
        oos_rows = simulate(d, oos_events, oos_cfg, val_end, n)
        if oos_rows:
            trades = pd.concat([trades, pd.DataFrame(oos_rows)], ignore_index=True)
            pd.DataFrame(oos_rows).to_csv(OUT / "selected_oos_trades.csv", index=False)
            oos_note = "One pre-selected validation-passing candidate evaluated once on OOS. " + json.dumps(metrics(pd.DataFrame(oos_rows), 12))
        else:
            oos_note = "A candidate passed selection, but no eligible OOS trades were generated."
        trades.to_csv(OUT / "trades.csv", index=False)

    metadata = {
        "symbol": "BTCUSD",
        "timeframe": "15m execution; 1h confirmed external swing levels; completed 4h EMA regime",
        "rows_15m": len(d), "rows_1h_complete": len(h1),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps_15m": gaps, "dataset_sha256": dataset_hash,
        "train_end_utc": str(d.index[train_end - 1]),
        "validation_end_utc": str(d.index[val_end - 1]),
        "oos_start_utc": str(d.index[val_end]),
        "matrix_configurations": len(configs),
        "fixed_structure_baseline": {"external_pivot_strength": 3, "local_pivot_strength": 3, "mss_wait_bars": 8},
        "fvg_event_counts_by_displacement_mode": event_counts,
        "train_eligible": len(eligible), "shortlisted": len(shortlist),
        "validation_pass": len(passed),
        "selected_oos_config": None if selected is None else selected.config_id,
        "oos_evaluated": bool(passed),
        "fvg_definition": {
            "bullish": "low of MSS candle > high two 15m candles earlier",
            "bearish": "high of MSS candle < low two 15m candles earlier",
            "entry": "limit placed only after MSS close; retracement depth 50% or 75% from proximal FVG edge",
            "expiry": "8 subsequent 15m candles; unfilled order is cancelled",
            "same_bar_ambiguity": "if a limit fills intrabar and target is also touched in that OHLC candle, no TP credit is given on the fill candle; stop is still honoured" ,
        },
        "displacement": "MSS directional body >= 0.5 or 0.75 ATR14 and close in directional outer quartile",
        "stop": "beyond full sweep-to-MSS excursion plus 0 or 0.1 x ATR14 at sweep",
        "target": "1.5R, 2R or 3R",
        "max_hold": "32 15m candles (8h) after fill",
        "cost_sensitivity_bps": list(COSTS),
        "cost_assumption": "6/12/20bp round-trip; no funding or separate spread/slippage",
        "split": "chronological 70/15/15; fixed 3/3 pivots and 8-bar MSS wait; 48-entry/exit/filter configurations; train screen, top-10 shortlist, validation; untouched OOS evaluated once only if a candidate passes both gates",
        "selection": {
            "train": ">=40 trades, net_R>0, PF>=1.05, max DD no worse than -25R, >=50% positive active months",
            "validation": ">=20 trades, net_R>0, PF>=1.05, max DD no worse than -15R, >=50% positive active months",
            "shortlist": "top 10 by train net_R/(abs(max_drawdown_R)+1)",
        },
        "limitations": "12bp is assumed, not fee-tier verified; no funding or separate spread/slippage; fixed UTC-free session (all hours); mechanical swing/MSS/FVG rules are not discretionary SMC; stop-first OHLC ambiguity; one pending order/position at a time per configuration",
    }
    (OUT / "methodology.json").write_text(json.dumps(metadata, indent=2))
    (OUT / "oos_status.txt").write_text(oos_note)

    print("METHODOLOGY")
    print(json.dumps(metadata, indent=2))
    print("\nTOP TRAIN (12bp)")
    print(tr[tr.trades > 0].sort_values("net_R", ascending=False).head(12).to_string(index=False))
    print("\nTOP VALIDATION (12bp)")
    print(va[va.trades > 0].sort_values("net_R", ascending=False).head(12).to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)} SHORTLIST={len(shortlist)} VALIDATION PASS={len(passed)}")
    print(oos_note)
    print(f"Artifacts: {OUT}/summary.csv, trades.csv, monthly_summary.csv, regime_summary.csv, methodology.json")


if __name__ == "__main__":
    main()
