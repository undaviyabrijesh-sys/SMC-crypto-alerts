#!/usr/bin/env python3
"""BTCUSD 1H/15m EMA51 pullback-break trigger study; research only.

Mechanical short rule: when completed 1H price is below EMA51, a green 15m
candle intersects a tolerance band around 15m EMA51; mark its low and sell a
break of that low. Stop is above the signal candle high plus a point buffer.
Long logic is the exact mirror. Entries are stop orders active only on later
15m candles, filled at trigger or adverse gap open.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
HOUR = pd.Timedelta(hours=1)
EMA_LEN = 51
ATR_LEN = 14
MAX_HOLD = 32
TOUCH_MODES = ("range_intersects",)
TOUCH_TOLERANCES = (0.10, 0.20)
ENTRY_EXPIRIES = (3, 6)
STOP_BUFFERS = (0.0, 25.0, 50.0)
TARGETS_R = (1.5, 2.0, 3.0)
DIRECTIONS = ("short_only", "long_only")
SESSIONS = ("all", "07-19")
HTF_FILTERS = ("ema_side", "ema_side_slope")
COSTS = (6, 12, 20)
MIN_TRAIN, MIN_VALIDATION = 40, 20


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_ohlcv(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    if d.timestamp.duplicated().any():
        raise ValueError("duplicate BTC timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="raise")
    v = d[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(v).all() or (v <= 0).any():
        raise ValueError("non-finite or non-positive BTC OHLC")
    bad = (d.high < d[["open", "close", "low"]].max(axis=1)) | (d.low > d[["open", "close", "high"]].min(axis=1))
    if bad.any():
        raise ValueError(f"invalid OHLC rows: {int(bad.sum())}")
    if d.index.to_series().diff().dropna().ne(BAR).any():
        raise ValueError("15m data gap detected; split the dataset before this study, do not fill")
    if "volume" in d:
        d["volume"] = pd.to_numeric(d.volume, errors="raise")
        if not np.isfinite(d.volume.to_numpy(float)).all() or (d.volume < 0).any():
            raise ValueError("invalid volume")
    return d


def rma(series: pd.Series, length: int) -> pd.Series:
    a = series.to_numpy(float)
    out = np.full(len(a), np.nan)
    if len(a) < length or not np.isfinite(a[:length]).all():
        return pd.Series(out, index=series.index)
    out[length - 1] = float(a[:length].mean())
    for i in range(length, len(a)):
        if np.isfinite(a[i]):
            out[i] = (out[i - 1] * (length - 1) + a[i]) / length
    return pd.Series(out, index=series.index)


def prepare_features(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    prev = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - prev).abs(), (d.low - prev).abs()], axis=1).max(axis=1)
    d["atr15"] = rma(tr, ATR_LEN)
    d["ema51_15m"] = d.close.ewm(span=EMA_LEN, adjust=False, min_periods=EMA_LEN).mean()

    hourly_rows = []
    for hour, g in d.groupby(d.index.floor("h"), sort=True):
        expected = pd.date_range(hour, periods=4, freq="15min", tz="UTC")
        if len(g) == 4 and g.index.equals(expected):
            hourly_rows.append({
                "available_time": hour + HOUR,
                "open": float(g.open.iloc[0]), "high": float(g.high.max()),
                "low": float(g.low.min()), "close": float(g.close.iloc[-1]),
            })
    if not hourly_rows:
        raise ValueError("no complete 1H candles")
    h = pd.DataFrame(hourly_rows).set_index("available_time").sort_index()
    h["segment"] = h.index.to_series().diff().ne(HOUR).cumsum().astype(int)
    h["ema51_1h"] = np.nan
    for _, g in h.groupby("segment", sort=False):
        h.loc[g.index, "ema51_1h"] = g.close.ewm(span=EMA_LEN, adjust=False, min_periods=EMA_LEN).mean().to_numpy()
    h["ema51_slope4"] = h.ema51_1h - h.ema51_1h.shift(4)

    signal_close_times = d.index + BAR
    for col in ("close", "ema51_1h", "ema51_slope4"):
        d[f"htf_{col}"] = h[col].reindex(signal_close_times, method="ffill").to_numpy()
    d["htf_regime"] = np.select(
        [d.htf_close > d.htf_ema51_1h, d.htf_close < d.htf_ema51_1h],
        ["bull", "bear"], default="range_or_unavailable",
    )
    return d


def session_ok(ts: pd.Timestamp, session: str) -> bool:
    return session == "all" or 7 <= ts.hour < 19


def build_signals(d: pd.DataFrame, cfg: dict) -> list[dict]:
    o, h, l, c = (d[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    ema, atr = d.ema51_15m.to_numpy(float), d.atr15.to_numpy(float)
    hclose = d.htf_close.to_numpy(float)
    hema = d.htf_ema51_1h.to_numpy(float)
    hslope = d.htf_ema51_slope4.to_numpy(float)
    valid = (np.isfinite(ema) & np.isfinite(atr) & (atr > 0)
             & np.isfinite(hclose) & np.isfinite(hema))
    tol = float(cfg["touch_tolerance_atr"]) * atr
    if cfg["touch_mode"] == "wick_near":
        short_touch = np.abs(h - ema) <= tol
        long_touch = np.abs(l - ema) <= tol
    else:
        short_touch = (l <= ema + tol) & (h >= ema - tol)
        long_touch = short_touch
    short_trend = valid & (hclose < hema)
    long_trend = valid & (hclose > hema)
    if cfg["htf_filter"] == "ema_side_slope":
        short_trend &= np.isfinite(hslope) & (hslope < 0)
        long_trend &= np.isfinite(hslope) & (hslope > 0)
    short_mask = valid & (c > o) & short_touch & short_trend
    long_mask = valid & (c < o) & long_touch & long_trend
    if cfg["direction"] == "short_only":
        long_mask[:] = False
    elif cfg["direction"] == "long_only":
        short_mask[:] = False
    short_idx = np.flatnonzero(short_mask)
    long_idx = np.flatnonzero(long_mask)
    out = []
    for i in short_idx:
        out.append({"signal_i": int(i), "side": -1, "trigger": float(l[i]),
                    "signal_extreme": float(h[i]), "atr": float(atr[i]),
                    "regime": str(d.htf_regime.iloc[i])})
    for i in long_idx:
        out.append({"signal_i": int(i), "side": 1, "trigger": float(h[i]),
                    "signal_extreme": float(l[i]), "atr": float(atr[i]),
                    "regime": str(d.htf_regime.iloc[i])})
    return sorted(out, key=lambda x: x["signal_i"])


def entry_fill(side: int, o: float, h: float, l: float, trigger: float, stop: float):
    if side == -1:
        if o >= stop:
            return None, "cancel_stop_gap"
        if o <= trigger:
            return o, "entry_gap"
        if l <= trigger:
            return trigger, "entry_trigger"
    else:
        if o <= stop:
            return None, "cancel_stop_gap"
        if o >= trigger:
            return o, "entry_gap"
        if h >= trigger:
            return trigger, "entry_trigger"
    return None, "pending"


def exit_fill(side: int, o: float, h: float, l: float, stop: float, target: float):
    if side == -1:
        if o >= stop:
            return max(o, stop), "SL"
        if h >= stop:
            return stop, "SL"
        if o <= target or l <= target:
            return target, "TP"
    else:
        if o <= stop:
            return min(o, stop), "SL"
        if l <= stop:
            return stop, "SL"
        if o >= target or h >= target:
            return target, "TP"
    return None, None


def simulate(d: pd.DataFrame, signals: list[dict], cfg: dict, split_name: str,
             bounds: dict, cost_bps: int) -> pd.DataFrame:
    start_i, end_i = bounds[split_name]
    o, h, l, c = (d[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    rows, blocked_until = [], start_i - 1
    for sig in signals:
        si = sig["signal_i"]
        if si < start_i or si < blocked_until:
            continue
        if not session_ok(d.index[si] + BAR, cfg["session"]):
            continue
        entry_start = si + 1
        expiry_end = min(entry_start + int(cfg["entry_expiry_bars"]), end_i - MAX_HOLD + 1)
        if entry_start >= end_i or expiry_end <= entry_start:
            continue
        side = int(sig["side"])
        trigger = float(sig["trigger"])
        stop = (float(sig["signal_extreme"]) + float(cfg["stop_buffer_points"])
                if side == -1 else float(sig["signal_extreme"]) - float(cfg["stop_buffer_points"]))
        filled = False
        cancelled = False
        for j in range(entry_start, expiry_end):
            fill, status = entry_fill(side, float(o[j]), float(h[j]), float(l[j]), trigger, stop)
            if status == "cancel_stop_gap":
                blocked_until = j
                cancelled = True
                break
            if status == "pending":
                continue
            entry = float(fill)
            risk = stop - entry if side == -1 else entry - stop
            if not np.isfinite(risk) or risk <= 0 or risk / entry > 0.05:
                blocked_until = j
                cancelled = True
                break
            target = entry - float(cfg["target_r"]) * risk if side == -1 else entry + float(cfg["target_r"]) * risk
            exit_price, outcome, exit_i = None, None, None
            for k in range(j, j + MAX_HOLD):
                px, why = exit_fill(side, float(o[k]), float(h[k]), float(l[k]), stop, target)
                if why:
                    exit_price, outcome, exit_i = float(px), why, k
                    break
            if exit_i is None:
                exit_i = j + MAX_HOLD - 1
                exit_price, outcome = float(c[exit_i]), "TIME"
            gross_r = (entry - exit_price) / risk if side == -1 else (exit_price - entry) / risk
            cost_r = (cost_bps / 10000.0) / (risk / entry)
            net_r = gross_r - cost_r
            rows.append({
                "split": split_name, "signal_time": d.index[si] + BAR,
                "entry_time": d.index[j], "exit_time": d.index[exit_i],
                "side": "short" if side == -1 else "long", "entry_type": status,
                "trigger": trigger, "entry": entry, "stop": stop, "target": target,
                "exit": exit_price, "outcome": outcome, "risk_points": risk,
                "gross_R": gross_r, "cost_R": cost_r, "net_R": net_r,
                "cost_bps_round_trip": cost_bps, "hold_bars": exit_i - j + 1,
                "regime": sig["regime"], **cfg,
            })
            blocked_until = exit_i
            filled = True
            break
        if not filled and not cancelled:
            blocked_until = max(blocked_until, expiry_end - 1)
    return pd.DataFrame(rows)


def metrics(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "profit_factor": None,
                "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
                "max_losing_streak": 0, "positive_month_fraction": 0.0,
                "TP": 0, "SL": 0, "TIME": 0}
    x = t.sort_values("entry_time")
    r = x.net_R.to_numpy(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = np.cumsum(r)
    dd = eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]
    streak = mx = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        mx = max(mx, streak)
    monthly = x.assign(month=x.exit_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {"trades": len(x), "win_rate_pct": float((r > 0).mean() * 100),
            "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and -losses.sum() > 0 else None,
            "net_R": float(r.sum()), "avg_R": float(r.mean()),
            "max_drawdown_R": float(dd.min()), "max_losing_streak": int(mx),
            "positive_month_fraction": float((monthly > 0).mean()) if len(monthly) else 0.0,
            "TP": int((x.outcome == "TP").sum()), "SL": int((x.outcome == "SL").sum()),
            "TIME": int((x.outcome == "TIME").sum())}


def split_bounds(n: int) -> dict:
    a, b = int(n * 0.70), int(n * 0.85)
    return {"train": (0, a), "validation": (a, b), "oos": (b, n)}


def run(csv: Path, out: Path):
    raw = load_ohlcv(csv)
    d = prepare_features(raw)
    bounds = split_bounds(len(d))
    values = itertools.product(TOUCH_MODES, TOUCH_TOLERANCES, ENTRY_EXPIRIES,
        STOP_BUFFERS, TARGETS_R, DIRECTIONS, SESSIONS, HTF_FILTERS)
    configs = [{"touch_mode": a, "touch_tolerance_atr": b, "entry_expiry_bars": c,
        "stop_buffer_points": e, "target_r": f, "direction": g,
        "session": h, "htf_filter": i} for a,b,c,e,f,g,h,i in values]
    matrix, cost_rows = [], []
    signal_cache = {}
    def signals_for(cfg):
        key = (cfg["touch_mode"], cfg["touch_tolerance_atr"], cfg["direction"], cfg["htf_filter"])
        if key not in signal_cache:
            signal_cache[key] = build_signals(d, cfg)
        return signal_cache[key]
    for cfg in configs:
        sigs = signals_for(cfg)
        tr = simulate(d, sigs, cfg, "train", bounds, 12)
        va = simulate(d, sigs, cfg, "validation", bounds, 12)
        tm, vm = metrics(tr), metrics(va)
        row = dict(cfg)
        row.update({f"train_{k}": v for k,v in tm.items()})
        row.update({f"validation_{k}": v for k,v in vm.items()})
        tg = (tm["trades"] >= MIN_TRAIN and tm["profit_factor"] is not None
              and tm["profit_factor"] >= 1.05 and tm["net_R"] > 0
              and tm["positive_month_fraction"] >= 0.50 and tm["max_drawdown_R"] >= -20)
        vg = (vm["trades"] >= MIN_VALIDATION and vm["profit_factor"] is not None
              and vm["profit_factor"] >= 1.05 and vm["net_R"] > 0
              and vm["positive_month_fraction"] >= 0.50 and vm["max_drawdown_R"] >= -12)
        row["train_gate"], row["validation_gate"] = bool(tg), bool(tg and vg)
        matrix.append(row)
        if tg:
            for sp in ("train", "validation"):
                for cost in COSTS:
                    t = simulate(d, sigs, cfg, sp, bounds, cost)
                    cost_rows.append({**cfg, "split": sp, "cost_bps_round_trip": cost, **metrics(t)})
    md = pd.DataFrame(matrix)
    out.mkdir(parents=True, exist_ok=True)
    md.to_csv(out / "matrix.csv", index=False)

    diag, monthly, regimes = [], [], []
    specs = [("best_train_net", md.sort_values("train_net_R", ascending=False).iloc[0])]
    enough = md[md.validation_trades >= MIN_VALIDATION]
    if not enough.empty:
        specs.append(("best_validation_min20", enough.sort_values(
            ["validation_profit_factor", "validation_net_R"], ascending=False).iloc[0]))
    for label, selected in specs:
        cfg = {k: selected[k] for k in configs[0]}
        sigs = signals_for(cfg)
        for sp in ("train", "validation"):
            for cost in COSTS:
                ct = simulate(d, sigs, cfg, sp, bounds, cost)
                cost_rows.append({"diagnostic_label": label, **cfg,
                    "split": sp, "cost_bps_round_trip": cost, **metrics(ct)})
            t = simulate(d, sigs, cfg, sp, bounds, 12)
            if t.empty:
                continue
            t["diagnostic_label"] = label
            diag.append(t)
            for month, g in t.assign(month=t.exit_time.dt.strftime("%Y-%m")).groupby("month"):
                monthly.append({"candidate": label, "split": sp, "month": month,
                    "trades": len(g), "net_R": float(g.net_R.sum())})
            for regime, g in t.groupby("regime"):
                regimes.append({"candidate": label, "split": sp, "regime": regime,
                    "trades": len(g), "net_R": float(g.net_R.sum())})
    if diag:
        pd.concat(diag, ignore_index=True).to_csv(out / "diagnostic_trades_12bp.csv", index=False)
    pd.DataFrame(monthly).to_csv(out / "diagnostic_monthly.csv", index=False)
    pd.DataFrame(regimes).to_csv(out / "diagnostic_regimes.csv", index=False)

    passes = md[md.validation_gate]
    selected_cfg = None
    if not passes.empty:
        selected = passes.sort_values(["validation_profit_factor", "validation_net_R"], ascending=False).iloc[0]
        selected_cfg = {k: selected[k] for k in configs[0]}
        sigs = signals_for(selected_cfg)
        for cost in COSTS:
            t = simulate(d, sigs, selected_cfg, "oos", bounds, cost)
            cost_rows.append({**selected_cfg, "split": "oos", "cost_bps_round_trip": cost, **metrics(t)})
    pd.DataFrame(cost_rows).to_csv(out / "cost_sensitivity.csv", index=False)

    meta = {"classification": "experimental BTC intraday backtest; no live use",
        "rows": len(raw), "start_utc": raw.index.min().isoformat(), "end_utc": raw.index.max().isoformat(),
        "csv_sha256": sha256(csv), "gap_count": int(raw.index.to_series().diff().dropna().ne(BAR).sum()),
        "zero_volume": int((raw.volume == 0).sum()) if "volume" in raw else None,
        "train_end_utc": raw.index[bounds['train'][1]].isoformat(),
        "validation_end_utc": raw.index[bounds['validation'][1]].isoformat(),
        "split": "chronological 70/15/15 by candle-open row index; full 8h trade horizon must remain inside split",
        "configurations": len(configs), "training_eligible": int(md.train_gate.sum()),
        "validation_passes": int(md.validation_gate.sum()), "oos_evaluated": selected_cfg is not None,
        "selected_config": selected_cfg,
        "signal": "completed 1H price vs EMA51; completed 15m green candle for short/red for long whose range intersects the 15m EMA51 band (0.1/0.2 ATR); mark signal low/high; enter only on a later break within 3/6 bars",
        "stops_targets": "signal candle high + 0/25/50 points for short; low - buffer for long; 1.5R/2R/3R; max hold 8h",
        "filters": "1H EMA51 side only or side plus 4h EMA slope; both directions tested separately; all hours or 07:00-19:00 UTC",
        "execution": "stop-entry fills at trigger or worse opening gap; pending entry cancelled if open gaps through stop; same-bar stop first; adverse stop gap at worse open; target at target; timeout at final close; one pending/active position at a time",
        "costs": "6/12/20bp assumed round-trip single-leg costs; 12bp primary; no funding/contract-specific settlement PnL; diagnostic cost sensitivity is not used for candidate selection",
        "selection_gates": "train >=40 trades, PF>=1.05, net R>0, positive months>=50%, DD>=-20R; validation >=20 trades, PF>=1.05, net R>0, positive months>=50%, DD>=-12R; OOS only after pass",
        "limitations": ["EMA touch interpretation is parameterized; exact 50-point buffer is included.",
            "No separate spread/order-book model; fixed round-trip cost sensitivity only.",
            "Intrabar sequence after stop-entry is unknowable from OHLC; stop-first when stop and target both touched."]}
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    print("\nTRAIN-ELIGIBLE\n", md[md.train_gate].to_string(index=False) if md.train_gate.any() else "none")
    print("\nVALIDATION-PASSES\n", md[md.validation_gate].to_string(index=False) if md.validation_gate.any() else "none")


def self_test():
    assert entry_fill(-1, 101, 102, 98, 99, 105) == (99, "entry_trigger")
    assert entry_fill(-1, 98, 100, 97, 99, 105) == (98, "entry_gap")
    assert entry_fill(-1, 106, 108, 97, 99, 105) == (None, "cancel_stop_gap")
    assert entry_fill(1, 99, 102, 98, 101, 95) == (101, "entry_trigger")
    assert entry_fill(1, 102, 104, 100, 101, 95) == (102, "entry_gap")
    assert entry_fill(1, 94, 103, 92, 101, 95) == (None, "cancel_stop_gap")
    assert exit_fill(-1, 100, 106, 90, 105, 90) == (105, "SL")
    assert exit_fill(-1, 107, 110, 95, 105, 90) == (107, "SL")
    assert exit_fill(-1, 100, 102, 85, 105, 90) == (90, "TP")
    assert exit_fill(1, 100, 110, 94, 95, 110) == (95, "SL")
    assert exit_fill(1, 93, 115, 90, 95, 110) == (93, "SL")
    assert exit_fill(1, 100, 115, 98, 95, 110) == (110, "TP")
    idx = pd.date_range("2025-01-01 00:00", periods=8, freq="15min", tz="UTC")
    raw = pd.DataFrame({"open":np.arange(100,108,dtype=float),
        "high":np.arange(101,109,dtype=float), "low":np.arange(99,107,dtype=float),
        "close":np.arange(100.5,108.5,1,dtype=float), "volume":1.0}, index=idx)
    feat = prepare_features(raw)
    assert pd.isna(feat.htf_ema51_1h.iloc[0])
    assert pd.isna(feat.htf_ema51_1h.iloc[2])
    assert pd.isna(feat.htf_ema51_1h.iloc[3])
    longer = pd.concat([raw, raw.iloc[-1:].assign(open=200, high=201, low=199, close=200.5).set_axis([idx[-1]+BAR])])
    f1, f2 = prepare_features(raw), prepare_features(longer)
    assert np.allclose(f1.ema51_15m.to_numpy(), f2.ema51_15m.iloc[:len(raw)].to_numpy(), equal_nan=True)
    n = 50
    ix = pd.date_range("2025-02-01", periods=n, freq="15min", tz="UTC")
    dummy = pd.DataFrame({"open":100.0,"high":101.0,"low":95.0,"close":100.0}, index=ix)
    dummy.loc[ix[9], "low"] = 89.0
    cfg = {"session":"all", "entry_expiry_bars":12, "stop_buffer_points":0.0, "target_r":2.0,
           "touch_mode":"range_intersects", "touch_tolerance_atr":0.1, "direction":"short_only", "htf_filter":"ema_side"}
    sig = [{"signal_i":7,"side":-1,"trigger":90.0,"signal_extreme":110.0,"atr":1.0,"regime":"bear"}]
    assert simulate(dummy, sig, cfg, "train", {"train":(0,40)}, 12).empty
    print("13 stop-entry, execution-order, split-boundary and causality self-tests passed")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--self-test", action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test(); return
    if not a.csv or not a.output_dir:
        p.error("provide --csv and --output-dir")
    run(a.csv, a.output_dir)

if __name__ == "__main__":
    main()
