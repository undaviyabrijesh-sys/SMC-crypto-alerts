"""BTCUSD 15m failed-Donchian-breakout reversal research.

A close outside a prior channel is treated as a failed breakout only if price
closes back inside the same frozen channel boundary within a short window.
Entry is next-bar open in the reversal direction. Research-only.
"""
import argparse
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
VOL_REGIME_FILTERS = ("all", "low", "mid", "high")
VOL_LOOKBACK = 2880  # 30 days of 15m bars
VOL_MIN_PERIODS = 720  # 7.5 days before regime labels are emitted
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
    source_segment = d.segment.resample("1h", label="right", closed="left").first()
    h = h.loc[counts.eq(4) & seg_counts.eq(1)].dropna()
    h["source_segment"] = source_segment.reindex(h.index).astype(int)
    hseg = h.index.to_series().diff().ne(pd.Timedelta("1h")).cumsum()
    h["ema50"] = h.groupby(hseg).close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    h["ema200"] = h.groupby(hseg).close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    hctx = h[["close", "ema50", "ema200", "source_segment"]].reindex(
        d.index, method="ffill"
    )
    # Do not carry a completed hourly candle or EMA across a raw-data gap.
    same_segment = hctx.source_segment.eq(d.segment)
    hctx.loc[~same_segment, ["close", "ema50", "ema200"]] = np.nan
    d["h_close"] = hctx.close
    d["h_ema50"] = hctx.ema50
    d["h_ema200"] = hctx.ema200
    bull = (d.h_close > d.h_ema50) & (d.h_ema50 > d.h_ema200)
    bear = (d.h_close < d.h_ema50) & (d.h_ema50 < d.h_ema200)
    d["regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )

    # Causal volatility regime: compare current ATR/price only with prior
    # observations from the same contiguous segment. Quantile baselines are
    # shifted one bar so the current candle cannot influence its own threshold.
    d["atr_pct"] = d.atr14 / d.close
    d["vol_q33"] = np.nan
    d["vol_q67"] = np.nan
    d["vol_regime"] = "unavailable"
    for _, g in d.groupby("segment", sort=False):
        q33 = g.atr_pct.rolling(
            VOL_LOOKBACK, min_periods=VOL_MIN_PERIODS
        ).quantile(0.33).shift(1)
        q67 = g.atr_pct.rolling(
            VOL_LOOKBACK, min_periods=VOL_MIN_PERIODS
        ).quantile(0.67).shift(1)
        d.loc[g.index, "vol_q33"] = q33.to_numpy()
        d.loc[g.index, "vol_q67"] = q67.to_numpy()
    valid_vol = d[["atr_pct", "vol_q33", "vol_q67"]].notna().all(axis=1)
    d.loc[valid_vol & (d.atr_pct <= d.vol_q33), "vol_regime"] = "low"
    d.loc[valid_vol & (d.atr_pct > d.vol_q33) & (d.atr_pct <= d.vol_q67), "vol_regime"] = "mid"
    d.loc[valid_vol & (d.atr_pct > d.vol_q67), "vol_regime"] = "high"
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


def resolve_exit(side, open_price, high, low, stop, target):
    """Conservative OHLC fill: stop first, with adverse stop-gap execution."""
    if side == "short":
        if high >= stop:
            return max(open_price, stop), "SL"
        if low <= target:
            return target, "TP"
    else:
        if low <= stop:
            return min(open_price, stop), "SL"
        if high >= target:
            return target, "TP"
    return None, None


def self_test():
    # Same-bar stop and target: stop must win for both directions.
    assert resolve_exit("long", 100, 120, 80, 90, 110) == (90, "SL")
    assert resolve_exit("short", 100, 120, 80, 110, 90) == (110, "SL")
    # Adverse stop gaps fill at the worse opening price.
    assert resolve_exit("long", 85, 95, 80, 90, 110) == (85, "SL")
    assert resolve_exit("short", 115, 120, 112, 110, 90) == (115, "SL")
    # Target fills at target, not at a favourable opening gap.
    assert resolve_exit("long", 115, 120, 112, 90, 110) == (110, "TP")
    assert resolve_exit("short", 85, 88, 80, 110, 90) == (90, "TP")

    # A synthetic gap must reset the hourly context and volatility baseline.
    rng = np.random.default_rng(19)
    idx1 = pd.date_range("2024-01-01", periods=1000, freq="15min", tz="UTC")
    idx2 = pd.date_range(idx1[-1] + pd.Timedelta(hours=2), periods=1000, freq="15min", tz="UTC")
    idx = idx1.append(idx2)
    close = 50000 + np.cumsum(rng.normal(0, 12, len(idx)))
    op = np.r_[close[0], close[:-1]]
    raw = pd.DataFrame({
        "open": op, "high": np.maximum(op, close) + 5,
        "low": np.minimum(op, close) - 5, "close": close,
    }, index=idx)
    prepared = prepare(raw)
    assert prepared.loc[idx2[0], "h_close"] != prepared.loc[idx2[0], "h_close"]
    assert prepared.loc[idx2[0], "vol_regime"] == "unavailable"

    # Future perturbations cannot change previously computed volatility labels.
    changed = raw.copy()
    cut = idx1[800]
    changed.loc[changed.index > cut, ["open", "high", "low", "close"]] *= 1.08
    altered = prepare(changed)
    compare = prepared.index <= cut
    assert prepared.loc[compare, "vol_regime"].equals(altered.loc[compare, "vol_regime"])
    print("8 failed-breakout execution, gap-reset and volatility-causality tests passed")


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
        observed_vol_regime = str(d.vol_regime.iloc[ei])
        if (
            cfg["vol_regime_filter"] != "all"
            and observed_vol_regime != cfg["vol_regime_filter"]
        ):
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
            fill, reason = resolve_exit(
                side, float(op[k]), float(hi[k]), float(lo[k]), stop, target
            )
            if reason:
                outcome = reason
                exit_price = float(fill)
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
            "vol_regime_filter": cfg["vol_regime_filter"],
            "vol_regime": observed_vol_regime,
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
    # Never touch OOS during the configuration sweep. It is reserved for
    # one candidate only after both chronological selection gates pass.
    samples = (
        ("train", 0, train_end),
        ("validation", train_end, val_end),
    )
    dataset_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    event_cache = {}
    for ch, fw, confirm in itertools.product(CHANNELS, FAIL_WINDOWS, CONFIRMATIONS):
        event_cache[(ch, fw, confirm)] = build_events(d, ch, fw, confirm)

    configs = []
    for values in itertools.product(
        CHANNELS, FAIL_WINDOWS, CONFIRMATIONS, STOP_BUFFERS, TARGETS,
        HTF_FILTERS, DIRECTIONS, SESSIONS, VOL_REGIME_FILTERS
    ):
        ch, fw, confirm, sb, target, htf, direction, session, vol_filter = values
        cfg_id = (
            f"dc{ch}_fail{fw}_{confirm}_stopbuf{sb}_{target}R_"
            f"{htf}_{direction}_{session}_vol{vol_filter}"
        )
        configs.append(dict(
            config_id=cfg_id, channel=ch, fail_window=fw,
            confirmation=confirm, stop_buffer=sb, target_r=target,
            htf_filter=htf, direction=direction, session=session,
            vol_regime_filter=vol_filter,
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
        "volatility_regime_filter_values": list(VOL_REGIME_FILTERS),
        "volatility_regime_definition": "ATR14/close classified against prior 30-day rolling 33rd/67th percentiles, min 7.5d observations, shifted one 15m bar and reset at every data gap",
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
    print(tr[tr.trades > 0].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print("\nTOP VALIDATION (12bp, nonzero trades)")
    print(va[va.trades > 0].sort_values("net_R", ascending=False).head(15).to_string(index=False))
    print(f"\nTRAIN ELIGIBLE={len(eligible)} SHORTLIST={len(shortlist)} VALIDATION PASS={len(passed)}")
    print(oos_note)
    print(f"Artifacts: {OUT}/summary.csv, trades.csv, monthly_summary.csv, regime_summary.csv, methodology.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        main()
