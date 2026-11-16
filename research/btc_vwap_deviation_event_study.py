from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

API = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL = "BTCUSD"
DAYS = 730
BAR = pd.Timedelta(minutes=5)
HORIZONS = {"1h": 12, "4h": 48}
COSTS = (6, 12, 20)
THRESHOLDS = (1.5, 2.0)
PRIMARY = 1.5
BOOT = 2000
SEED = 20261116


def digest(df):
    h = hashlib.sha256()
    for i in range(0, len(df), 100000):
        h.update(df.iloc[i:i+100000].to_csv().encode())
    return h.hexdigest()


def normalize(raw):
    n = len(raw)
    d = raw.copy()
    if "timestamp" not in d:
        d["timestamp"] = pd.to_datetime(pd.to_numeric(d.pop("time"), errors="coerce"), unit="s", utc=True)
    elif pd.api.types.is_numeric_dtype(d["timestamp"]):
        d["timestamp"] = pd.to_datetime(pd.to_numeric(d["timestamp"], errors="coerce"), unit="s", utc=True)
    else:
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True, errors="coerce")
    badts = int(d.timestamp.isna().sum())
    d = d.dropna(subset=["timestamp"])
    dup = int(d.timestamp.duplicated().sum())
    d = d.drop_duplicates("timestamp", keep="last").sort_values("timestamp").set_index("timestamp")
    if "volume" not in d:
        d["volume"] = 0.0
        missing = len(d)
    else:
        d["volume"] = pd.to_numeric(d.volume, errors="coerce")
        missing = int(d.volume.isna().sum())
        d["volume"] = d.volume.fillna(0.0)
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    a = d[["open", "high", "low", "close"]].to_numpy(float)
    finite = np.isfinite(a).all(1)
    positive = (d[["open", "high", "low", "close"]] > 0).all(axis=1).to_numpy()
    shape = ((d.high >= d[["open", "close", "low"]].max(axis=1)) &
             (d.low <= d[["open", "close", "high"]].min(axis=1))).to_numpy()
    badnf = int((~finite).sum())
    badpos = int((finite & ~positive).sum())
    badshape = int((finite & positive & ~shape).sum())
    d = d.loc[finite & positive & shape, ["open", "high", "low", "close", "volume"]]
    d = d[d.index + BAR <= pd.Timestamp.now(tz="UTC")]
    if d.empty:
        raise RuntimeError("No valid closed BTC 5m candles")
    delta = d.index.to_series().diff().dropna()
    q = {
        "source_rows": n, "valid_rows": len(d),
        "start_utc": d.index.min().isoformat(), "end_utc": d.index.max().isoformat(),
        "duplicates_removed": dup, "invalid_timestamps": badts,
        "invalid_nonfinite_ohlc": badnf, "invalid_nonpositive_ohlc": badpos,
        "invalid_ohlc_shape": badshape, "missing_volume": missing,
        "zero_volume": int((d.volume == 0).sum()),
        "gap_count": int((delta != BAR).sum()),
        "largest_gap_minutes": float(delta.max().total_seconds()/60) if len(delta) else 0.0,
        "sha256": digest(d)
    }
    return d, q


def fetch():
    end = int(pd.Timestamp.now(tz="UTC").timestamp())
    start = end - DAYS * 86400
    cur = start
    frames = []
    total = 0
    while cur < end:
        stop = min(cur + 1800 * 300, end)
        r = requests.get(API, params={"resolution": "5m", "symbol": SYMBOL, "start": cur, "end": stop},
                         headers={"Accept": "application/json", "User-Agent": "SaltyQuant-VWAP/1.0"}, timeout=45)
        r.raise_for_status()
        p = r.json()
        if p.get("success") is not True:
            raise RuntimeError(f"Delta API error: {p}")
        rows = p.get("result") or []
        if rows:
            frames.append(pd.DataFrame(rows))
            total += len(rows)
        cur = stop
        time.sleep(0.08)
    if not frames:
        raise RuntimeError("Delta returned no BTC candles")
    d, q = normalize(pd.concat(frames, ignore_index=True))
    q["source_rows"] = total
    return d, q


def add_segments(d):
    z = d.copy()
    z["seg"] = z.index.to_series().diff().ne(BAR).cumsum().astype(int)
    return z


def resample_complete(d, rule, count):
    kw = {"label": "right", "closed": "left"}
    z = d[["open", "high", "low", "close", "volume"]].resample(rule, **kw).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    n = d.close.resample(rule, **kw).count()
    s = d.seg.resample(rule, **kw).nunique()
    z = z.loc[n.eq(count) & s.eq(1)].dropna(subset=["open", "high", "low", "close"])
    z["seg"] = z.index.to_series().diff().ne(pd.Timedelta(rule)).cumsum().astype(int)
    return z


def features(raw):
    d = add_segments(raw)
    prev_close = d.groupby("seg").close.shift(1)
    tr = pd.concat([d.high-d.low, (d.high-prev_close).abs(), (d.low-prev_close).abs()], axis=1).max(axis=1)
    d["tr"] = tr
    d["atr14_prior"] = d.groupby("seg").tr.transform(
        lambda s: s.ewm(alpha=1/14, adjust=False, min_periods=14).mean().shift(1))
    typical = (d.high + d.low + d.close) / 3.0
    day = d.index.floor("D")
    pv = pd.Series(typical.to_numpy() * d.volume.to_numpy(), index=d.index).groupby(day).cumsum()
    vv = d.volume.groupby(day).cumsum()
    d["vwap"] = pv / vv.where(vv > 0)
    d["dev_atr"] = (d.close - d.vwap) / d.atr14_prior
    d["prev_dev_atr"] = d.groupby("seg").dev_atr.shift(1)
    rng = (d.high - d.low).replace(0, np.nan)
    d["close_loc"] = (d.close - d.low) / rng

    h4 = resample_complete(d, "4h", 48)
    h4["ema50"] = h4.groupby("seg").close.transform(lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean())
    h4["ema200"] = h4.groupby("seg").close.transform(lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean())
    bull = (h4.close > h4.ema50) & (h4.ema50 > h4.ema200)
    bear = (h4.close < h4.ema50) & (h4.ema50 < h4.ema200)
    h4["regime"] = np.select([bull, bear], ["bull", "bear"], default="neutral")
    d["regime"] = h4.regime.reindex(d.index, method="ffill").fillna("neutral")
    return d


def build_events(d, threshold):
    rows = []
    dev = d.dev_atr.to_numpy(float)
    prev = d.prev_dev_atr.to_numpy(float)
    op = d.open.to_numpy(float)
    cl = d.close.to_numpy(float)
    loc = d.close_loc.to_numpy(float)
    seg = d.seg.to_numpy()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    for i in range(1, len(d)-1):
        if not np.isfinite(dev[i]) or not np.isfinite(prev[i]) or seg[i] != seg[i+1]:
            continue
        side = None
        if prev[i] >= threshold and 0.0 < dev[i] < threshold and cl[i] < op[i] and loc[i] <= 0.5:
            side = "short"
        elif prev[i] <= -threshold and -threshold < dev[i] < 0.0 and cl[i] > op[i] and loc[i] >= 0.5:
            side = "long"
        if side is None:
            continue
        entry_time = d.index[i+1]
        if entry_time < next_allowed:
            continue
        rows.append({"signal_i": i, "entry_i": i+1, "time": entry_time, "side": side,
                     "regime": str(d.regime.iloc[i+1]), "date": entry_time.date().isoformat(),
                     "bucket": int(entry_time.hour//3), "entry": float(op[i+1]),
                     "signal_dev_atr": float(dev[i]), "threshold_atr": float(threshold)})
        next_allowed = entry_time + pd.Timedelta(hours=8)
    return pd.DataFrame(rows)


def build_controls(d, event_signals, threshold):
    dev = d.dev_atr.to_numpy(float)
    prev = d.prev_dev_atr.to_numpy(float)
    op = d.open.to_numpy(float)
    cl = d.close.to_numpy(float)
    loc = d.close_loc.to_numpy(float)
    seg = d.seg.to_numpy()
    event_i = set(event_signals.signal_i.astype(int).tolist()) if len(event_signals) else set()
    rows = []
    for i in range(1, len(d)-1):
        if i in event_i or not np.isfinite(dev[i]) or not np.isfinite(prev[i]) or seg[i] != seg[i+1]:
            continue
        side = None
        if 0.5 <= prev[i] <= 1.0 and dev[i] >= 0.25 and cl[i] < op[i] and loc[i] <= 0.5:
            side = "short"
        elif -1.0 <= prev[i] <= -0.5 and dev[i] <= -0.25 and cl[i] > op[i] and loc[i] >= 0.5:
            side = "long"
        if side is None:
            continue
        t = d.index[i+1]
        rows.append({"signal_i": i, "entry_i": i+1, "time": t, "side": side,
                     "regime": str(d.regime.iloc[i+1]), "date": t.date().isoformat(),
                     "bucket": int(t.hour//3), "entry": float(op[i+1]),
                     "signal_dev_atr": float(dev[i]), "threshold_atr": float(threshold)})
    return pd.DataFrame(rows)


def split_bounds(n):
    a, b = int(n*0.70), int(n*0.85)
    return {"development": (0, a), "validation": (a, b), "untouched_oos_not_evaluated": (b, n)}


def forward_returns(d, signals, start, end, sample):
    rows = []
    if signals.empty:
        return pd.DataFrame()
    for r in signals.itertuples(index=False):
        i = int(r.entry_i)
        if i < start or i >= end:
            continue
        rec = {"entry_i": i, "time": pd.Timestamp(r.time), "side": r.side, "regime": r.regime,
               "date": r.date, "bucket": int(r.bucket), "entry": float(r.entry),
               "signal_dev_atr": float(r.signal_dev_atr), "threshold_atr": float(r.threshold_atr),
               "sample": sample}
        valid = True
        for horizon, bars in HORIZONS.items():
            j = i + bars - 1
            if j >= end or d.seg.iloc[j] != d.seg.iloc[i]:
                valid = False
                break
            direction = 1.0 if r.side == "long" else -1.0
            rec[horizon] = direction * (float(d.close.iloc[j]) / float(r.entry) - 1.0) * 10000.0
        if valid:
            rows.append(rec)
    return pd.DataFrame(rows)


def exclude_near_events(controls, events):
    if controls.empty or events.empty:
        return controls.copy()
    et = pd.DatetimeIndex(events.time).sort_values()
    keep = []
    for t in pd.DatetimeIndex(controls.time):
        k = et.searchsorted(t)
        near = (k < len(et) and abs((et[k]-t).total_seconds()) <= 1800) or (k > 0 and abs((et[k-1]-t).total_seconds()) <= 1800)
        keep.append(not near)
    return controls.loc[np.asarray(keep, dtype=bool)].reset_index(drop=True)


def match_pairs(events, controls):
    if events.empty or controls.empty:
        return pd.DataFrame()
    groups = {k: g.sort_values("time").reset_index(drop=True)
              for k, g in controls.groupby(["date", "side", "regime", "bucket"])}
    used = set()
    rows = []
    for _, e in events.sort_values("time").iterrows():
        key = (e.date, e.side, e.regime, int(e.bucket))
        g = groups.get(key)
        if g is None:
            continue
        a = g[~g.entry_i.isin(used)]
        if a.empty:
            continue
        delta = (a.time - e.time).abs()
        m = delta.min()
        c = a.loc[delta.eq(m)].sort_values("time").iloc[0]
        used.add(int(c.entry_i))
        row = {"event_i": int(e.entry_i), "event_time": e.time.isoformat(),
               "control_i": int(c.entry_i), "control_time": c.time.isoformat(),
               "side": e.side, "date": e.date, "regime": e.regime, "bucket": int(e.bucket),
               "distance_min": float(m.total_seconds()/60), "threshold_atr": float(e.threshold_atr)}
        for h in HORIZONS:
            row[h+"_event"] = float(e[h])
            row[h+"_control"] = float(c[h])
            row[h+"_lift"] = float(e[h] - c[h])
        rows.append(row)
    return pd.DataFrame(rows)


def bootstrap_ci(pairs, horizon):
    if pairs.empty:
        return (None, None)
    by_day = {k: g[horizon+"_lift"].to_numpy(float) for k, g in pairs.groupby("date")}
    days = list(by_day)
    if len(days) < 2:
        return (None, None)
    rng = np.random.default_rng(SEED)
    vals = np.empty(BOOT)
    for i in range(BOOT):
        chosen = rng.choice(days, len(days), replace=True)
        vals[i] = np.mean(np.concatenate([by_day[x] for x in chosen]))
    return tuple(map(float, np.quantile(vals, [0.025, 0.975])))


def metrics(x, times, cost):
    v = x.to_numpy(float) - cost if len(x) else np.array([])
    if not len(v):
        return {"events": 0, "win_rate_pct": None, "pf": None, "mean_net_bps": None,
                "median_net_bps": None, "event_sequence_max_dd_bps": None,
                "max_losing_streak": None, "positive_month_fraction": None,
                "positive_months": 0, "active_months": 0}
    wins, losses = v[v > 0], v[v < 0]
    pf = float(wins.sum()/abs(losses.sum())) if len(losses) else (float("inf") if len(wins) else 0.0)
    eq = np.cumsum(v)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    dd = eq - peak
    streak = mx = 0
    for z in v:
        streak = streak + 1 if z < 0 else 0
        mx = max(mx, streak)
    months = pd.to_datetime(pd.Series(times), utc=True).dt.to_period("M").astype(str)
    monthly = pd.Series(v).groupby(months.to_numpy()).sum()
    return {"events": len(v), "win_rate_pct": float((v > 0).mean()*100),
            "pf": pf, "mean_net_bps": float(v.mean()), "median_net_bps": float(np.median(v)),
            "event_sequence_max_dd_bps": float(dd.min()), "max_losing_streak": mx,
            "positive_month_fraction": float((monthly > 0).mean()),
            "positive_months": int((monthly > 0).sum()), "active_months": len(monthly)}


def evaluate_threshold(d, all_events, all_controls, spans, threshold):
    summary, event_frames, pair_frames = [], [], []
    for sample in ("development", "validation"):
        start, end = spans[sample]
        e = forward_returns(d, all_events, start, end, sample)
        c = forward_returns(d, all_controls, start, end, sample)
        c = exclude_near_events(c, e)
        pairs = match_pairs(e, c)
        if not e.empty:
            event_frames.append(e)
        if not pairs.empty:
            pair_frames.append(pairs.assign(sample=sample, threshold_atr=threshold))
        for h in HORIZONS:
            lo, hi = bootstrap_ci(pairs, h) if not pairs.empty else (None, None)
            for cost in COSTS:
                m = metrics(e[h] if not e.empty else pd.Series(dtype=float),
                            e.time if not e.empty else pd.Series(dtype="datetime64[ns, UTC]"), cost)
                summary.append({"threshold_atr": threshold, "sample": sample, "horizon": h,
                                "cost_bps": cost, "matched_pairs": len(pairs),
                                "matched_event_mean_gross_bps": float(pairs[h+"_event"].mean()) if not pairs.empty else None,
                                "matched_control_mean_gross_bps": float(pairs[h+"_control"].mean()) if not pairs.empty else None,
                                "mean_lift_bps": float(pairs[h+"_lift"].mean()) if not pairs.empty else None,
                                "lift_ci95_low_bps": lo, "lift_ci95_high_bps": hi, **m})
    ev = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    pa = pd.concat(pair_frames, ignore_index=True) if pair_frames else pd.DataFrame()
    return summary, ev, pa


def frozen_gate(summary):
    s = pd.DataFrame(summary)
    out = {}
    for h in HORIZONS:
        a = s[(s.threshold_atr == PRIMARY) & (s["sample"] == "development") &
              (s.horizon == h) & (s.cost_bps == 12)]
        b = s[(s.threshold_atr == PRIMARY) & (s["sample"] == "validation") &
              (s.horizon == h) & (s.cost_bps == 12)]
        if a.empty or b.empty:
            out[h] = {"passes": False}
            continue
        a, b = a.iloc[0], b.iloc[0]
        def ok(x, min_events, min_pairs):
            return (x.events >= min_events and x.matched_pairs >= min_pairs and
                    pd.notna(x.mean_net_bps) and x.mean_net_bps > 0 and
                    pd.notna(x.mean_lift_bps) and x.mean_lift_bps > 0 and
                    pd.notna(x.lift_ci95_low_bps) and x.lift_ci95_low_bps > 0 and
                    pd.notna(x.positive_month_fraction) and x.positive_month_fraction >= 0.5)
        dp, vp = ok(a, 100, 50), ok(b, 30, 20)
        out[h] = {"development_pass": bool(dp), "validation_pass": bool(vp),
                  "passes": bool(dp and vp), "development_events": int(a.events),
                  "development_pairs": int(a.matched_pairs), "validation_events": int(b.events),
                  "validation_pairs": int(b.matched_pairs)}
    return {"primary_threshold_atr": PRIMARY, "any_horizon_passes_both_gates": any(x["passes"] for x in out.values()),
            "horizons": out, "oos_evaluated": False}


def breakdown(ev, out):
    if ev.empty:
        return
    x = ev.copy()
    x["month"] = pd.to_datetime(x.time, utc=True).dt.to_period("M").astype(str)
    monthly, regimes, sides = [], [], []
    for (threshold, sample), base in x.groupby(["threshold_atr", "sample"]):
        for h in HORIZONS:
            for cost in COSTS:
                g = base.copy()
                g["net_bps"] = g[h] - cost
                for month, a in g.groupby("month"):
                    monthly.append({"threshold_atr": threshold, "sample": sample, "horizon": h,
                                    "cost_bps": cost, "month": month, "events": len(a),
                                    "net_bps_sum": a.net_bps.sum(), "net_bps_mean": a.net_bps.mean()})
                for regime, a in g.groupby("regime"):
                    regimes.append({"threshold_atr": threshold, "sample": sample, "horizon": h,
                                    "cost_bps": cost, "regime": regime, "events": len(a),
                                    "net_bps_sum": a.net_bps.sum(), "net_bps_mean": a.net_bps.mean()})
                for (side, regime), a in g.groupby(["side", "regime"]):
                    sides.append({"threshold_atr": threshold, "sample": sample, "horizon": h,
                                  "cost_bps": cost, "side": side, "regime": regime,
                                  "events": len(a), "net_bps_sum": a.net_bps.sum(),
                                  "net_bps_mean": a.net_bps.mean()})
    pd.DataFrame(monthly).to_csv(out/"vwap_monthly.csv", index=False)
    pd.DataFrame(regimes).to_csv(out/"vwap_regimes.csv", index=False)
    pd.DataFrame(sides).to_csv(out/"vwap_side_regimes.csv", index=False)


def run(out):
    out.mkdir(parents=True, exist_ok=True)
    raw, quality = fetch()
    if len(raw) < 80000:
        raise RuntimeError(f"Only {len(raw)} valid 5m bars; need approximately two years")
    d = features(raw)
    spans = split_bounds(len(d))
    all_summary, all_events, all_pairs, all_confirmed, all_controls = [], [], [], [], []
    for threshold in THRESHOLDS:
        ev = build_events(d, threshold)
        co = build_controls(d, ev, threshold)
        all_confirmed.append(ev.assign(threshold_atr=threshold))
        all_controls.append(co.assign(threshold_atr=threshold))
        sm, er, pa = evaluate_threshold(d, ev, co, spans, threshold)
        all_summary.extend(sm)
        if not er.empty:
            all_events.append(er)
        if not pa.empty:
            all_pairs.append(pa)
    summary = pd.DataFrame(all_summary)
    er = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame()
    pairs = pd.concat(all_pairs, ignore_index=True) if all_pairs else pd.DataFrame()
    confirmed = pd.concat(all_confirmed, ignore_index=True) if all_confirmed else pd.DataFrame()
    controls = pd.concat(all_controls, ignore_index=True) if all_controls else pd.DataFrame()
    summary.to_csv(out/"vwap_summary.csv", index=False)
    er.to_csv(out/"vwap_event_returns.csv", index=False)
    pairs.to_csv(out/"vwap_matched_pairs.csv", index=False)
    confirmed.to_csv(out/"vwap_confirmed_events.csv", index=False)
    controls.to_csv(out/"vwap_control_candidates.csv", index=False)
    breakdown(er, out)
    gate = frozen_gate(all_summary)
    metadata = {
        "classification": "experimental BTC 5m UTC-day VWAP deviation/reclaim event study; not a trading system",
        "instrument": "Delta Exchange India BTCUSD perpetual traded-price OHLCV",
        "dataset": quality,
        "split": {"method": "chronological 70/15/15 by valid 5m row index",
                  "development_end_row": spans["development"][1],
                  "validation_end_row": spans["validation"][1],
                  "untouched_oos_range": list(spans["untouched_oos_not_evaluated"]),
                  "oos_evaluated": False},
        "vwap": "UTC calendar-day reset; cumulative typical-price*volume / cumulative volume",
        "atr": "Wilder ATR(14), shifted one bar so current signal candle is excluded from its own normalizer",
        "primary_rules": {
            "threshold_atr": PRIMARY,
            "upper": "previous close deviation >= +1.5 prior ATR; current close returns below +1.5 ATR but remains above VWAP; bearish candle closing in lower half",
            "lower": "previous close deviation <= -1.5 prior ATR; current close returns above -1.5 ATR but remains below VWAP; bullish candle closing in upper half",
            "entry": "next 5m open after signal candle closes",
            "cooldown": "one global event stream, 8 hours across directions",
            "max_holding": "event-study horizon only; 1h and 4h forward returns"
        },
        "diagnostic_threshold_atr": 2.0,
        "control_rules": "non-event moderate deviation 0.5-1.0 prior ATR, same directional rejection candle, current close at least 0.25 ATR from VWAP; next 5m open",
        "matching": {"ratio": "1:1 without replacement",
                     "keys": ["UTC date", "direction", "completed 4h EMA50/EMA200 regime", "3h UTC bucket"],
                     "exclude_near_event_minutes": 30, "tie_break": "earlier timestamp",
                     "bootstrap": f"{BOOT} UTC-day cluster replicates, seed {SEED}"},
        "costs_round_trip_bps": list(COSTS),
        "funding": "excluded; historical settlement cashflow mapping not verified",
        "spread_slippage": "not separately modelled; flat cost sensitivities only",
        "gate": gate,
        "r_not_applicable": True,
        "decision": "only a primary 1.5 ATR horizon passing both chronological gates may proceed to a separately frozen stop/target study; otherwise reject/rethink; untouched OOS not evaluated"
    }
    (out/"metadata.json").write_text(json.dumps(metadata, indent=2, default=str)+"\n")
    print(json.dumps(metadata, indent=2, default=str))
    print(summary.to_string(index=False))


def self_test():
    # UTC-day VWAP must reset at midnight and use volume weights.
    ix = pd.date_range("2026-01-01T23:50:00Z", periods=4, freq="5min")
    x = pd.DataFrame({"open":[100,101,200,202], "high":[101,102,201,203],
                      "low":[99,100,199,201], "close":[100,101,200,202],
                      "volume":[1,3,2,2]}, index=ix)
    f = features(x)
    assert abs(f.vwap.iloc[2] - 200.0) < 1e-9
    assert abs(f.vwap.iloc[3] - 201.0) < 1e-9

    # Future perturbation must not alter earlier VWAP, ATR or deviation features.
    n = 1000
    idx = pd.date_range("2026-01-01T00:00:00Z", periods=n, freq="5min")
    base = 50000 + np.cumsum(np.sin(np.arange(n)/13)*5 + 0.2)
    raw = pd.DataFrame({"open":base, "high":base+8, "low":base-8,
                        "close":base+1, "volume":100+np.arange(n)%17}, index=idx)
    a = features(raw)
    altered = raw.copy()
    altered.iloc[800:, altered.columns.get_loc("close")] *= 1.02
    altered.iloc[800:, altered.columns.get_loc("high")] *= 1.02
    b = features(altered)
    cols = ["vwap", "atr14_prior", "dev_atr", "prev_dev_atr"]
    pd.testing.assert_frame_equal(a[cols].iloc[:800], b[cols].iloc[:800])

    # A gap creates a new segment; a signal cannot be generated across it.
    gap = raw.drop(idx[500])
    sg = add_segments(gap)
    assert sg.seg.iloc[499] != sg.seg.iloc[500]

    # A synthetic upper-band inward reclaim creates a short signal on next bar open.
    toy = pd.DataFrame({
        "open":[100,100,100,100,100], "high":[101,110,106,103,102],
        "low":[99,99,98,98,99], "close":[100,108,104,101,101],
        "volume":[10,10,10,10,10], "seg":[1,1,1,1,1],
        "dev_atr":[0,1.8,1.2,0.8,0.7], "prev_dev_atr":[0,0,1.8,1.2,0.8],
        "close_loc":[0.5,0.9,0.45,0.4,0.5], "regime":["neutral"]*5
    }, index=pd.date_range("2026-01-01T00:00:00Z", periods=5, freq="5min"))
    ev = build_events(toy, 1.5)
    assert len(ev) == 1 and ev.iloc[0].side == "short" and ev.iloc[0].entry_i == 3

    # A control can only be selected once in matching.
    e = pd.DataFrame([{"entry_i":10,"time":pd.Timestamp("2026-01-01T00:50Z"),"side":"short",
                       "regime":"bull","date":"2026-01-01","bucket":0,"threshold_atr":1.5,
                       "1h":2.0,"4h":3.0}])
    c = pd.DataFrame([{"entry_i":9,"time":pd.Timestamp("2026-01-01T00:45Z"),"side":"short",
                       "regime":"bull","date":"2026-01-01","bucket":0,"threshold_atr":1.5,
                       "1h":1.0,"4h":2.0}])
    p = match_pairs(e,c)
    assert len(p) == 1 and p.iloc[0].control_i == 9
    print("VWAP event-study synthetic tests passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, default=Path("results/btc-vwap-event-study"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        run(args.output_dir)
