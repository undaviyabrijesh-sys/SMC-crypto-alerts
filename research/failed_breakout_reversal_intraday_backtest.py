"""BTCUSD 15m failed-Donchian-breakout reversal research.

A close outside a prior channel is treated as a failed breakout only if price
closes back inside the same frozen channel boundary within a short window.
Entry is next-bar open in the reversal direction. Research-only.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("failed_breakout_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
MAX_HOLD = 32
COSTS = (6, 12, 20)
CHANNELS = (20, 55)
FAIL_WINDOWS = (1, 3)
CONFIRMATIONS = ("close_inside", "opposite_body")
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
        for n in CHANNELS:
            d.loc[g.index, f"dc{n}_high"] = g.high.shift(1).rolling(
                n, min_periods=n
            ).max().to_numpy()
            d.loc[g.index, f"dc{n}_low"] = g.low.shift(1).rolling(
                n, min_periods=n
            ).min().to_numpy()

    # Only complete 1h bars built from four contiguous 15m candles.
    h = d[["open", "high", "low", "close"]].resample(
        "1h", label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample("1h", label="right", closed="left").count()
    seg_counts = d.segment.resample("1h", label="right", closed="left").nunique()
    h = h.loc[counts.eq(4) & seg_counts.eq(1)].dropna()
    hseg = h.index.to_series().diff().ne(pd.Timedelta("1h")).cumsum()
    h["ema50"] = h.groupby(hseg).close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    h["ema200"] = h.groupby(hseg).close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    for c in ("close", "ema50", "ema200"):
        d[f"h_{c}"] = h[c].reindex(d.index, method="ffill")
    bull = (d.h_close > d.h_ema50) & (d.h_ema50 > d.h_ema200)
    bear = (d.h_close < d.h_ema50) & (d.h_ema50 < d.h_ema200)
    d["regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )
    return d


def build_events(d, channel, fail_window, confirmation):
    """Build causal failed-breakout events using a frozen breakout boundary."""
    hi = d[f"dc{channel}_high"].to_numpy(float)
    lo = d[f"dc{channel}_low"].to_numpy(float)
    op = d.open.to_numpy(float)
    cl = d.close.to_numpy(float)
    bh = d.high.to_numpy(float)
    bl = d.low.to_numpy(float)
    atr = d.atr14.to_numpy(float)
    seg = d.segment.to_numpy()
    events = []

    for i in range(1, len(d) - fail_window - 1):
        if seg[i - 1] != seg[i] or not np.isfinite([hi[i], lo[i], atr[i]]).all():
            continue
        up_break = cl[i] > hi[i] and cl[i - 1] <= hi[i - 1]
        down_break = cl[i] < lo[i] and cl[i - 1] >= lo[i - 1]
        if up_break == down_break:  # neither or both: ignore
            continue
        boundary = float(hi[i] if up_break else lo[i])
        extreme = float(bh[i] if up_break else bl[i])
        found = False

        for j in range(i + 1, min(i + fail_window + 1, len(d) - 1)):
            if seg[j] != seg[i] or seg[j + 1] != seg[i]:
                break
            if up_break:
                extreme = max(extreme, float(bh[j]))
                back_inside = cl[j] < boundary
                opposite = cl[j] < op[j]
                side = "short"
            else:
                extreme = min(extreme, float(bl[j]))
                back_inside = cl[j] > boundary
                opposite = cl[j] > op[j]
                side = "long"

            confirmed = back_inside and (
                confirmation == "close_inside" or opposite
            )
            if not confirmed:
                continue

            entry_i = j + 1
            events.append({
                "breakout_i": i,
                "signal_i": j,
                "entry_i": entry_i,
                "side": side,
                "boundary": boundary,
                "extreme": extreme,
                "atr_signal": float(atr[j]),
                "channel": channel,
                "fail_window": fail_window,
                "confirmation": confirmation,
            })
            found = True
            break
        if found:
            continue
    return sorted(events, key=lambda e: e["entry_i"])


def trade_metrics(g, bps):
    if g.empty:
        return dict(trades=0, win_rate_pct=0.0, profit_factor=None, net_R=0.0,
                    avg_R=0.0, max_drawdown_R=0.0, max_losing_streak=0,
                    positive_month_fraction=0.0, TP=0, SL=0, TIME=0)
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
    hc = d.h_close.to_numpy(float)
    e50 = d.h_ema50.to_numpy(float)
    e200 = d.h_ema200.to_numpy(float)
    regime = d.regime.to_numpy()
    rows = []
    last_exit = start_i - 1

    for ev in events:
        bi, si, ei = ev["breakout_i"], ev["signal_i"], ev["entry_i"]
        # Require breakout, reclaim and full trade to belong to this split.
        if bi < start_i or si < start_i or ei >= end_i or ei <= last_exit:
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
            if not np.isfinite([hc[ei], e50[ei], e200[ei]]).all():
                continue
            aligned = (
                side == "long" and hc[ei] > e50[ei] > e200[ei]
            ) or (
                side == "short" and hc[ei] < e50[ei] < e200[ei]
            )
            if not aligned:
                continue

        end_trade = ei + MAX_HOLD
        if end_trade > end_i or end_trade > len(d):
            continue
        if not np.all(seg[ei:end_trade] == seg[ei]):
            continue

        entry = float(op[ei])
        buffer = cfg["stop_buffer"] * float(ev["atr_signal"])
        stop = (
            float(ev["extreme"]) + buffer if side == "short"
            else float(ev["extreme"]) - buffer
        )
        risk = stop - entry if side == "short" else entry - stop
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = (
            entry - cfg["target_r"] * risk if side == "short"
            else entry + cfg["target_r"] * risk
        )

        outcome = "TIME"
        exit_i = end_trade - 1
        exit_price = float(cl[exit_i])
        for k in range(ei, end_trade):
            stop_hit = hi[k] >= stop if side == "short" else lo[k] <= stop
            target_hit = lo[k] <= target if side == "short" else hi[k] >= target
            # Conservative ambiguity: stop takes priority over target.
            if stop_hit:
                outcome = "SL"
                exit_price = max(stop, float(op[k])) if side == "short" else min(stop, float(op[k]))
                exit_i = k
                break
            if target_hit:
                outcome = "TP"
                exit_price = target
                exit_i = k
                break

        gross = (entry - exit_price) / risk if side == "short" else (exit_price - entry) / risk
        row = {
            "config_id": cfg["config_id"],
            "channel": cfg["channel"],
            "fail_window": cfg["fail_window"],
            "confirmation": cfg["confirmation"],
            "stop_buffer": cfg["stop_buffer"],
            "target_r": cfg["target_r"],
            "htf_filter": cfg["htf_filter"],
            "direction": cfg["direction"],
            "session": cfg["session"],
            "sample": cfg["sample"],
            "side": side,
            "breakout_time": d.index[bi],
            "signal_time": d.index[si],
            "entry_time": entry_time,
            "exit_time": d.index[exit_i],
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
    d = prepare(raw)
    if len(d) < 10000:
        raise RuntimeError(f"Insufficient BTCUSD 15m data: {len(d)}")
    gaps = int((d.index.to_series().diff().dropna() != BAR).sum())
    n = len(d)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    samples = (
        ("train", 0, train_end),
        ("validation", train_end, val_end),
        ("oos", val_end, n),
    )
    dataset_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    event_cache = {}
    for ch, fw, confirm in itertools.product(CHANNELS, FAIL_WINDOWS, CONFIRMATIONS):
        event_cache[(ch, fw, confirm)] = build_events(d, ch, fw, confirm)

    configs = []
    for values in itertools.product(
        CHANNELS, FAIL_WINDOWS, CONFIRMATIONS, STOP_BUFFERS, TARGETS,
        HTF_FILTERS, DIRECTIONS, SESSIONS
    ):
        ch, fw, confirm, sb, target, htf, direction, session = values
        cfg_id = (
            f"dc{ch}_fail{fw}_{confirm}_stopbuf{sb}_{target}R_"
            f"{htf}_{direction}_{session}"
        )
        configs.append(dict(
            config_id=cfg_id, channel=ch, fail_window=fw,
            confirmation=confirm, stop_buffer=sb, target_r=target,
            htf_filter=htf, direction=direction, session=session,
        ))

    trade_rows, summary_rows, monthly_rows, regime_rows = [], [], [], []
    for cfg in configs:
        events = event_cache[(cfg["channel"], cfg["fail_window"], cfg["confirmation"])]
        for sample, start, end in samples:
            local = dict(cfg, sample=sample)
            rows = simulate(d, events, local, start, end)
            if rows:
                trade_rows.extend(rows)
            g = pd.DataFrame(rows)
            for bps in COSTS:
                summary_rows.append(dict(
                    **local, cost_bps=bps, **trade_metrics(g, bps)
                ))
            if not g.empty:
                x = g.copy()
                x["month"] = x.entry_time.dt.strftime("%Y-%m")
                for (month, bps), q in [
                    ((m, b), x.assign(_bps=b).groupby("month").get_group(m))
                    for m in x.month.unique() for b in COSTS
                ]:
                    r = q[f"net_R_{bps}bp"]
                    monthly_rows.append(dict(
                        config_id=cfg["config_id"], sample=sample,
                        month=month, cost_bps=bps, trades=len(q),
                        net_R=round(float(r.sum()), 2),
                    ))
                for (reg, bps), q in [
                    ((r, b), x[x.regime == r]) for r in x.regime.unique()
                    for b in COSTS
                ]:
                    if q.empty:
                        continue
                    r = q[f"net_R_{bps}bp"]
                    regime_rows.append(dict(
                        config_id=cfg["config_id"], sample=sample,
                        regime=reg, cost_bps=bps, trades=len(q),
                        net_R=round(float(r.sum()), 2),
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
            v.profit_factor is not None and v.profit_factor >= 1.05 and
            v.max_drawdown_R >= -15 and v.positive_month_fraction >= 0.50
        ):
            passed.append((candidate, v))

    oos_note = "OOS NOT EVALUATED: no candidate passed the pre-registered train/validation gates."
    selected = None
    if passed:
        selected = max(
            passed,
            key=lambda pair: pair[1].net_R / (abs(pair[1].max_drawdown_R) + 1)
        )[0]
        oos_cfg = dict(selected[[
            "config_id", "channel", "fail_window", "confirmation",
            "stop_buffer", "target_r", "htf_filter", "direction", "session"
        ]].to_dict(), sample="oos")
        oos_rows = simulate(
            d, event_cache[(oos_cfg["channel"], oos_cfg["fail_window"], oos_cfg["confirmation"])],
            oos_cfg, val_end, n
        )
        if oos_rows:
            trades = pd.concat([trades, pd.DataFrame(oos_rows)], ignore_index=True)
            pd.DataFrame(oos_rows).to_csv(OUT / "selected_oos_trades.csv", index=False)
            oos_metrics = trade_metrics(pd.DataFrame(oos_rows), 12)
            oos_note = "Selected one validation-passing candidate for a single OOS evaluation. " + json.dumps(oos_metrics)
        else:
            oos_note = "A candidate passed selection, but no eligible OOS trades were generated."
        trades.to_csv(OUT / "trades.csv", index=False)

    methodology = {
        "symbol": "BTCUSD", "timeframe": "15m", "rows": len(d),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps": gaps, "dataset_sha256": dataset_hash,
        "train_end_utc": str(d.index[train_end - 1]),
        "validation_end_utc": str(d.index[val_end - 1]),
        "oos_start_utc": str(d.index[val_end]),
        "matrix_configurations": len(configs),
        "train_eligible": len(eligible), "shortlisted": len(shortlist),
        "validation_pass": len(passed),
        "selected_oos_config": None if selected is None else selected.config_id,
        "oos_evaluated": bool(passed),
        "cost_sensitivity_bps": list(COSTS),
        "cost_assumption": "6/12/20bp round-trip sensitivity; no funding or separate spread/slippage",
        "execution": "15m close outside prior shifted Donchian 20/55 channel; first close back inside frozen boundary within 1/3 bars; optional opposite-body confirmation; enter next 15m open in reversal direction; stop beyond full breakout excursion plus 0/0.1 ATR; fixed 1.5/2/3/4R target; 8h max hold; stop-first ambiguity; adverse gap-through stop fill",
        "split": "chronological 70/15/15; train gate then top-25 shortlist then validation; one OOS evaluation only if a candidate passes both",
        "htf_context": "optional completed 1h EMA50/EMA200 alignment; only complete 4x15m hours; right-edge timestamp",
        "selection": {
            "train": ">=40 trades, net_R>0, PF>=1.05, max DD no worse than -25R",
            "validation": ">=20 trades, net_R>0, PF>=1.05, max DD no worse than -15R, >=50% positive active months",
            "shortlist": "top 25 by train net_R/(abs(max_drawdown_R)+1)"
        },
        "limitations": "12bp primary cost is assumed and actual fee tier unverified; 6/20bp sensitivity only; no funding or separate spread/slippage; fixed 07-19 UTC session proxy; OHLC ambiguity resolves stop first; channel and 1h context are causal and gap-segmented",
    }
    (OUT / "methodology.json").write_text(json.dumps(methodology, indent=2))
    (OUT / "oos_status.txt").write_text(oos_note)

    print("METHODOLOGY")
    print(json.dumps(methodology, indent=2))
    print("\nTOP TRAIN (12bp, nonzero trades)")
    print(tr.sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print("\nTOP VALIDATION (12bp, nonzero trades)")
    print(va[va.trades > 0].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)} SHORTLIST={len(shortlist)} VALIDATION PASS={len(passed)}")
    print(oos_note)
    print(f"Artifacts: {OUT}/summary.csv, trades.csv, monthly_summary.csv, regime_summary.csv, methodology.json")


if __name__ == "__main__":
    main()
