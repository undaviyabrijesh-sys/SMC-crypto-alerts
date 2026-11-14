"""BTCUSD 15m regular RSI-divergence + neckline-break research.

Pivots are confirmed only after right-side bars close. A regular bullish
divergence requires a lower confirmed pivot low with a higher RSI value;
a regular bearish divergence requires a higher pivot high with lower RSI.
Entry requires a subsequent close through the intervening neckline and is
filled at the next 15m open. Research only.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crt_backtest import fetch

OUT = Path("rsi_divergence_results")
OUT.mkdir(exist_ok=True)
BAR = pd.Timedelta("15min")
HOUR = pd.Timedelta("1h")
MAX_HOLD = 32
COSTS = (6, 12, 20)
PIVOTS = ((2, 2), (3, 3), (5, 5))
RSI_LENGTHS = (7, 14)
BREAK_WINDOWS = (3, 6)
STOP_BUFFERS = (0.0, 0.1)
TARGETS = (1.5, 2.0, 3.0)
HTF_FILTERS = ("none", "ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN = 40
MIN_VALIDATION = 20
MAX_SHORTLIST = 25


def wilder(values, length):
    x = np.asarray(values, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < length or not np.isfinite(x[:length]).all():
        return out
    out[length - 1] = float(np.mean(x[:length]))
    for i in range(length, len(x)):
        if not np.isfinite(x[i]):
            out[i] = np.nan
        elif np.isfinite(out[i - 1]):
            out[i] = (out[i - 1] * (length - 1) + x[i]) / length
    return out


def wilder_rsi(close, length):
    c = np.asarray(close, dtype=float)
    delta = np.r_[np.nan, np.diff(c)]
    gains = np.where(np.isfinite(delta), np.maximum(delta, 0.0), np.nan)
    losses = np.where(np.isfinite(delta), np.maximum(-delta, 0.0), np.nan)
    avg_gain = wilder(gains, length)
    avg_loss = wilder(losses, length)
    rs = np.divide(avg_gain, avg_loss, out=np.full(len(c), np.nan),
                   where=np.isfinite(avg_loss) & (avg_loss > 0))
    out = 100.0 - 100.0 / (1.0 + rs)
    out[np.isfinite(avg_loss) & (avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[np.isfinite(avg_loss) & (avg_loss == 0) & (avg_gain == 0)] = 50.0
    return out


def prepare(raw):
    d = raw.sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    for col in ("open", "high", "low", "close"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d[
        (d[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (d.high >= d[["open", "close", "low"]].max(axis=1))
        & (d.low <= d[["open", "close", "high"]].min(axis=1))
    ]
    d["segment"] = d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    d["atr14"] = np.nan
    d["rsi7"] = np.nan
    d["rsi14"] = np.nan
    prev_close = d.groupby("segment").close.shift(1)
    tr = pd.concat(
        [d.high - d.low, (d.high - prev_close).abs(),
         (d.low - prev_close).abs()], axis=1
    ).max(axis=1)
    for _, g in d.groupby("segment", sort=False):
        ix = g.index
        d.loc[ix, "atr14"] = wilder(tr.loc[ix].to_numpy(float), 14)
        d.loc[ix, "rsi7"] = wilder_rsi(g.close.to_numpy(float), 7)
        d.loc[ix, "rsi14"] = wilder_rsi(g.close.to_numpy(float), 14)

    # Build only complete 1h bars from four contiguous 15m candles.
    hourly = d[["open", "high", "low", "close"]].resample(
        "1h", label="right", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = d.close.resample("1h", label="right", closed="left").count()
    seg_counts = d.segment.resample("1h", label="right", closed="left").nunique()
    source_segment = d.segment.resample(
        "1h", label="right", closed="left"
    ).first()
    hourly = hourly.loc[counts.eq(4) & seg_counts.eq(1)].dropna()
    hourly["source_segment"] = source_segment.reindex(hourly.index).astype(int)
    hseg = (
        hourly.index.to_series().diff().ne(HOUR)
        | hourly.source_segment.ne(hourly.source_segment.shift())
    ).cumsum()
    hourly["ema50"] = hourly.groupby(hseg).close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    hourly["ema200"] = hourly.groupby(hseg).close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    ctx = hourly[["close", "ema50", "ema200", "source_segment"]].reindex(
        d.index, method="ffill"
    )
    same_segment = ctx.source_segment.eq(d.segment)
    ctx.loc[~same_segment, ["close", "ema50", "ema200"]] = np.nan
    d["h_close"] = ctx.close
    d["h_ema50"] = ctx.ema50
    d["h_ema200"] = ctx.ema200
    bull = (d.h_close > d.h_ema50) & (d.h_ema50 > d.h_ema200)
    bear = (d.h_close < d.h_ema50) & (d.h_ema50 < d.h_ema200)
    d["regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )
    return d


def confirmed_pivots(values, left, right, kind):
    """Return (pivot_index, confirmation_index) pairs; no future bars used."""
    x = np.asarray(values, dtype=float)
    out = []
    for p in range(left, len(x) - right):
        window_left = x[p-left:p]
        window_right = x[p+1:p+right+1]
        if not np.isfinite(x[p]) or not np.isfinite(window_left).all() or not np.isfinite(window_right).all():
            continue
        if kind == "low":
            valid = x[p] < np.min(window_left) and x[p] <= np.min(window_right)
        else:
            valid = x[p] > np.max(window_left) and x[p] >= np.max(window_right)
        if valid:
            out.append((p, p + right))
    return out


def divergence_events_segment(g, left, right, rsi_length, break_window):
    events = []
    rsi = g[f"rsi{rsi_length}"].to_numpy(float)
    close = g.close.to_numpy(float)
    high = g.high.to_numpy(float)
    low = g.low.to_numpy(float)
    atr = g.atr14.to_numpy(float)
    n = len(g)

    for kind in ("low", "high"):
        pivots = confirmed_pivots(low if kind == "low" else high, left, right, kind)
        previous = None
        for pivot_i, confirm_i in pivots:
            if previous is not None:
                prev_i, _ = previous
                if pivot_i - prev_i >= 2 and np.isfinite([rsi[pivot_i], rsi[prev_i], atr[pivot_i]]).all() and atr[pivot_i] > 0:
                    if kind == "low":
                        divergent = low[pivot_i] < low[prev_i] and rsi[pivot_i] > rsi[prev_i]
                        neckline = float(np.max(high[prev_i+1:pivot_i])) if pivot_i > prev_i + 1 else np.nan
                        side = "long"
                    else:
                        divergent = high[pivot_i] > high[prev_i] and rsi[pivot_i] < rsi[prev_i]
                        neckline = float(np.min(low[prev_i+1:pivot_i])) if pivot_i > prev_i + 1 else np.nan
                        side = "short"
                    if divergent and np.isfinite(neckline):
                        last_j = min(confirm_i + break_window, n - 2)
                        for j in range(confirm_i, last_j + 1):
                            crossed = (
                                close[j] > neckline and close[j-1] <= neckline
                                if side == "long"
                                else close[j] < neckline and close[j-1] >= neckline
                            )
                            if crossed and j + 1 < n:
                                events.append({
                                    "prior_pivot_i": prev_i,
                                    "pivot_i": pivot_i,
                                    "confirm_i": confirm_i,
                                    "signal_i": j,
                                    "entry_i": j + 1,
                                    "side": side,
                                    "neckline": neckline,
                                    "pivot_extreme": float(low[pivot_i] if side == "long" else high[pivot_i]),
                                    "pivot_atr": float(atr[pivot_i]),
                                    "pivot_rsi": float(rsi[pivot_i]),
                                    "prior_pivot_rsi": float(rsi[prev_i]),
                                })
                                break
            previous = (pivot_i, confirm_i)
    return sorted(events, key=lambda e: e["entry_i"])


def build_events(d, left, right, rsi_length, break_window):
    events = []
    offset = 0
    for _, g in d.groupby("segment", sort=False):
        local = divergence_events_segment(g, left, right, rsi_length, break_window)
        for e in local:
            events.append({k: (v + offset if k.endswith("_i") else v) for k, v in e.items()})
        offset += len(g)
    return sorted(events, key=lambda e: e["entry_i"])


def resolve_exit(side, op, hi, lo, stop, target):
    if side == "long":
        if lo <= stop:
            return min(op, stop), "SL"
        if hi >= target:
            return target, "TP"
    else:
        if hi >= stop:
            return max(op, stop), "SL"
        if lo <= target:
            return target, "TP"
    return None, None


def max_losing_streak(values):
    cur = best = 0
    for value in values:
        cur = cur + 1 if value < 0 else 0
        best = max(best, cur)
    return best


def metrics(trades, cost_bps):
    if trades.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "profit_factor": None,
                "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
                "max_losing_streak": 0, "positive_month_fraction": 0.0}
    x = trades.sort_values("entry_time")
    r = x.gross_R.to_numpy(float) - (x.entry.to_numpy(float) * cost_bps / 10000.0) / x.risk.to_numpy(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = np.cumsum(r)
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]
    monthly = pd.Series(r, index=x.entry_time).groupby(x.entry_time.dt.strftime("%Y-%m")).sum()
    return {
        "trades": int(len(x)),
        "win_rate_pct": round(float((r > 0).mean() * 100), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) and abs(losses.sum()) else None,
        "net_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "max_drawdown_R": round(float(min(0.0, dd.min())), 2),
        "max_losing_streak": int(max_losing_streak(r)),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3) if len(monthly) else 0.0,
    }


def simulate(d, events, cfg, start_i, end_i, cost_bps=12):
    op = d.open.to_numpy(float)
    hi = d.high.to_numpy(float)
    lo = d.low.to_numpy(float)
    cl = d.close.to_numpy(float)
    seg = d.segment.to_numpy()
    regime = d.regime.to_numpy()
    hclose = d.h_close.to_numpy(float)
    e50 = d.h_ema50.to_numpy(float)
    e200 = d.h_ema200.to_numpy(float)
    rows = []
    last_exit = start_i - 1
    for ev in events:
        pi, pprev, ci, si, ei = (
            ev["pivot_i"], ev["prior_pivot_i"], ev["confirm_i"],
            ev["signal_i"], ev["entry_i"]
        )
        # Both pivots and the complete trade must belong to this sample.
        if pprev < start_i or pi < start_i or ci < start_i or ei < start_i:
            continue
        if ei >= end_i or ei + MAX_HOLD >= end_i or ei <= last_exit:
            continue
        if seg[pprev] != seg[ei] or seg[pi] != seg[ei] or seg[ei + MAX_HOLD - 1] != seg[ei]:
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
            if not np.isfinite([hclose[si], e50[si], e200[si]]).all():
                continue
            if side == "long" and not (hclose[si] > e50[si] > e200[si]):
                continue
            if side == "short" and not (hclose[si] < e50[si] < e200[si]):
                continue
        entry = float(op[ei])
        pad = cfg["stop_buffer"] * float(ev["pivot_atr"])
        stop = float(ev["pivot_extreme"] - pad if side == "long" else ev["pivot_extreme"] + pad)
        risk = entry - stop if side == "long" else stop - entry
        if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
            continue
        target = entry + cfg["target_r"] * risk if side == "long" else entry - cfg["target_r"] * risk
        exit_price = None
        reason = None
        exit_i = None
        for j in range(ei, ei + MAX_HOLD):
            fill, why = resolve_exit(side, float(op[j]), float(hi[j]), float(lo[j]), stop, target)
            if why:
                exit_price, reason, exit_i = fill, why, j
                break
        if exit_i is None:
            exit_i = ei + MAX_HOLD - 1
            exit_price = float(cl[exit_i])
            reason = "TIME"
        gross_r = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
        rows.append({
            "prior_pivot_time": d.index[pprev], "pivot_time": d.index[pi],
            "confirm_time": d.index[ci], "signal_time": d.index[si],
            "entry_time": entry_time, "exit_time": d.index[exit_i],
            "side": side, "regime": str(regime[si]), "entry": entry,
            "stop": stop, "target": target, "exit": exit_price, "reason": reason,
            "risk": risk, "gross_R": gross_r, "cost_R": entry * cost_bps / 10000.0 / risk,
            "net_R": gross_r - entry * cost_bps / 10000.0 / risk,
            "rsi_pivot": ev["pivot_rsi"], "prior_pivot_rsi": ev["prior_pivot_rsi"],
            "neckline": ev["neckline"],
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def self_test():
    assert resolve_exit("long", 100, 120, 80, 90, 110) == (90, "SL")
    assert resolve_exit("short", 100, 120, 80, 110, 90) == (110, "SL")
    assert resolve_exit("long", 85, 95, 80, 90, 110) == (85, "SL")
    assert resolve_exit("short", 115, 120, 112, 110, 90) == (115, "SL")
    assert resolve_exit("long", 115, 120, 112, 90, 110) == (110, "TP")
    assert resolve_exit("short", 85, 88, 80, 110, 90) == (90, "TP")
    assert confirmed_pivots([5, 4, 3, 4, 5, 6], 2, 2, "low") == [(2, 4)]
    assert confirmed_pivots([1, 2, 3, 2, 1, 0], 2, 2, "high") == [(2, 4)]

    rng = np.random.default_rng(2026)
    i1 = pd.date_range("2024-01-01", periods=600, freq="15min", tz="UTC")
    i2 = pd.date_range(i1[-1] + pd.Timedelta(hours=2), periods=600, freq="15min", tz="UTC")
    idx = i1.append(i2)
    close = 50000 + np.cumsum(rng.normal(0, 15, len(idx)))
    op = np.r_[close[0], close[:-1]]
    raw = pd.DataFrame({
        "open": op, "high": np.maximum(op, close) + 8,
        "low": np.minimum(op, close) - 8, "close": close,
    }, index=idx)
    prepared = prepare(raw)
    assert prepared.segment.iloc[600] != prepared.segment.iloc[599]
    assert np.isnan(prepared.atr14.iloc[600])
    assert np.isnan(prepared.rsi14.iloc[600])
    assert np.isnan(prepared.h_close.iloc[600])

    cut = idx[450]
    changed = raw.copy()
    changed.loc[changed.index > cut, ["open", "high", "low", "close"]] *= 1.05
    altered = prepare(changed)
    mask = prepared.index <= cut
    for col in ("atr14", "rsi7", "rsi14", "h_ema50", "h_ema200"):
        np.testing.assert_allclose(
            prepared.loc[mask, col].to_numpy(float),
            altered.loc[mask, col].to_numpy(float),
            equal_nan=True,
        )
    print("10 RSI-divergence execution, pivot-confirmation, gap-reset and causality tests passed")


def run():
    raw = fetch("15m").sort_index()
    d = prepare(raw)
    if len(d) < 1000:
        raise RuntimeError("Insufficient BTCUSD 15m history")
    data_path = OUT / "BTCUSD_15m.csv"
    d.to_csv(data_path)
    split1 = int(len(d) * 0.70)
    split2 = int(len(d) * 0.85)
    boundaries = {"train_end": d.index[split1-1], "validation_end": d.index[split2-1],
                  "oos_start": d.index[split2]}
    configs = list(itertools.product(
        PIVOTS, RSI_LENGTHS, BREAK_WINDOWS, STOP_BUFFERS, TARGETS,
        HTF_FILTERS, DIRECTIONS, SESSIONS
    ))
    cache = {}
    matrix = []
    candidates = []
    for pivot, rsi_len, break_window, stop_buffer, target_r, htf, direction, session in configs:
        left, right = pivot
        key = (left, right, rsi_len, break_window)
        if key not in cache:
            cache[key] = build_events(d, left, right, rsi_len, break_window)
        cfg = {"pivot": f"{left}/{right}", "rsi_length": rsi_len,
               "break_window": break_window, "stop_buffer": stop_buffer,
               "target_r": target_r, "htf_filter": htf,
               "direction": direction, "session": session}
        train = simulate(d, cache[key], cfg, 0, split1, 12)
        val = simulate(d, cache[key], cfg, split1, split2, 12)
        mt = metrics(train, 12)
        mv = metrics(val, 12)
        row = {**cfg, **{f"train_{k}": v for k, v in mt.items()},
               **{f"validation_{k}": v for k, v in mv.items()}}
        train_gate = (
            mt["trades"] >= MIN_TRAIN and mt["net_R"] > 0
            and mt["profit_factor"] is not None and mt["profit_factor"] >= 1.05
            and mt["max_drawdown_R"] >= -25
            and mt["positive_month_fraction"] >= 0.50
        )
        row["train_gate"] = bool(train_gate)
        matrix.append(row)
        if train_gate:
            score = mt["net_R"] / (abs(mt["max_drawdown_R"]) + 1.0)
            candidates.append((score, cfg, cache[key], train, val, mt, mv))
    md = pd.DataFrame(matrix).sort_values(
        ["train_gate", "train_net_R"], ascending=[False, False]
    )
    md.to_csv(OUT / "matrix.csv", index=False)
    shortlist = sorted(candidates, key=lambda x: x[0], reverse=True)[:MAX_SHORTLIST]
    selected = []
    costs = []
    monthly_rows = []
    regime_rows = []
    for score, cfg, events, train12, val12, mt, mv in shortlist:
        val_gate = (
            mv["trades"] >= MIN_VALIDATION and mv["net_R"] > 0
            and mv["profit_factor"] is not None and mv["profit_factor"] >= 1.05
            and mv["max_drawdown_R"] >= -15
            and mv["positive_month_fraction"] >= 0.50
        )
        cfg_id = "|".join(str(cfg[k]) for k in cfg)
        for sample, start, end in (
            ("train", 0, split1), ("validation", split1, split2),
            ("oos", split2, len(d))
        ):
            if sample == "oos" and not val_gate:
                continue
            for bps in COSTS:
                trades = simulate(d, events, cfg, start, end, bps)
                m = metrics(trades, bps)
                costs.append({"config_id": cfg_id, **cfg, "sample": sample,
                              "cost_bps": bps, **m, "validation_gate": bool(val_gate)})
                if bps == 12 and not trades.empty:
                    x = trades.copy()
                    x["config_id"] = cfg_id
                    x["sample"] = sample
                    selected.append(x)
                    x["month"] = x.entry_time.dt.strftime("%Y-%m")
                    for month, g in x.groupby("month"):
                        monthly_rows.append({"config_id": cfg_id, **cfg,
                                             "sample": sample, "month": month,
                                             **metrics(g, 12)})
                    for regime_name, g in x.groupby("regime"):
                        regime_rows.append({"config_id": cfg_id, **cfg,
                                            "sample": sample, "regime": regime_name,
                                            **metrics(g, 12)})
    pd.DataFrame(costs).to_csv(OUT / "cost_sensitivity.csv", index=False)
    if selected:
        pd.concat(selected, ignore_index=True).to_csv(OUT / "shortlisted_trades_12bp.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(OUT / "monthly.csv", index=False)
    pd.DataFrame(regime_rows).to_csv(OUT / "regimes.csv", index=False)

    train_passes = int(md.train_gate.sum())
    validation_passes = sum(
        1 for _, cfg, _, _, _, _, mv in shortlist
        if mv["trades"] >= MIN_VALIDATION and mv["net_R"] > 0
        and mv["profit_factor"] is not None and mv["profit_factor"] >= 1.05
        and mv["max_drawdown_R"] >= -15 and mv["positive_month_fraction"] >= 0.50
    )
    meta = {
        "symbol": "BTCUSD", "timeframe": "15m", "rows": len(d),
        "start_utc": d.index.min().isoformat(), "end_utc": d.index.max().isoformat(),
        "gaps": int(d.index.to_series().diff().dropna().ne(BAR).sum()),
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "train_end_utc": boundaries["train_end"].isoformat(),
        "validation_end_utc": boundaries["validation_end"].isoformat(),
        "oos_start_utc": boundaries["oos_start"].isoformat(),
        "configurations": len(configs), "train_eligible": train_passes,
        "shortlisted": len(shortlist), "validation_passes": validation_passes,
        "oos_evaluated": bool(validation_passes),
        "costs_bps": list(COSTS), "primary_cost_bps": 12,
        "cost_assumption": "assumed round-trip taker friction per BTC leg; actual fee tier and separate spread/impact unverified; funding excluded",
        "signal": "regular divergence between consecutive confirmed 15m swing pivots; pivot is available only after right bars close; entry only after close crosses intervening neckline; next 15m open",
        "execution": "pivot-extreme stop plus 0/0.1 ATR14 buffer; fixed 1.5/2/3R; max 8h; one position/config; stop-first OHLC ambiguity; adverse stop-gap fill; no trade crosses data gap or sample boundary",
        "selection": "train >=40 trades, PF>=1.05, positive net R, max DD >=-25R, >=50% positive active months; shortlist top 25 by net_R/(abs(DD)+1); validation >=20, PF>=1.05, positive net R, max DD >=-15R, >=50% positive active months; OOS only after both",
        "limitations": ["15m OHLC only; pivot/neckline divergence is a mechanical regular-divergence proxy, not discretionary chart reading",
                       "no funding, separate spread or market-impact model; fixed UTC 07-19 session ignores DST",
                       "RSI and ATR warm up/reset within contiguous data segments; completed 1h EMA50/200 resets after gaps",
                       "no parameter selection from OOS; OOS omitted unless a candidate passes both gates"]
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("METHODOLOGY")
    print(json.dumps(meta, indent=2))
    print("\nTOP TRAIN (12bp)")
    print(md[md.train_gate].head(15).to_string(index=False))
    print("\nTOP VALIDATION DIAGNOSTICS (12bp)")
    if shortlist:
        diag = []
        for score, cfg, events, tr, va, mt, mv in shortlist:
            diag.append({**cfg, "train": mt, "validation": mv})
        print(json.dumps(diag[:10], indent=2, default=str))
    print(f"\nTRAIN ELIGIBLE={train_passes} SHORTLIST={len(shortlist)} VALIDATION PASS={validation_passes}")
    if not validation_passes:
        print("OOS NOT EVALUATED: no candidate passed the pre-registered train/validation gates.")
    else:
        print("OOS evaluated only for candidates passing both gates.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        run()


if __name__ == "__main__":
    main()
