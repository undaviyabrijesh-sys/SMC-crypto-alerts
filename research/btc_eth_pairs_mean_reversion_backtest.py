#!/usr/bin/env python3
"""BTC/ETH rolling-residual pair mean-reversion backtest; experimental only.

Signals are formed on completed 15m closes from a rolling, lagged hedge ratio
and lagged residual distribution. Both legs enter at the next 15m open.
No account access, orders, alerts, or production strategy changes.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
BETA_LOOKBACKS = (960, 2880)       # 10d / 30d
Z_LOOKBACKS = (288, 672)           # 3d / 7d
ENTRY_ZS = (1.5, 2.0, 2.5)
STOP_ZS = (3.5, 4.0)
TARGET_ZS = (0.0, 0.5)
MAX_HOLDS = (96, 192)              # 24h / 48h
DIRECTIONS = ("both", "long_spread_only", "short_spread_only")
CORR_FILTERS = (0.0, 0.6)
COSTS = (6, 12, 20)                # assumed round-trip bps per leg
MIN_TRAIN, MIN_VALIDATION = 40, 20


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_ohlcv(path: Path, label: str) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    if d["timestamp"].duplicated().any():
        raise ValueError(f"{label}: duplicate timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    for col in ("open", "high", "low", "close"):
        d[col] = pd.to_numeric(d[col], errors="raise")
    values = d[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError(f"{label}: non-finite or non-positive OHLC")
    bad = (
        (d.high < d[["open", "close", "low"]].max(axis=1))
        | (d.low > d[["open", "close", "high"]].min(axis=1))
    )
    if bad.any():
        raise ValueError(f"{label}: {int(bad.sum())} invalid OHLC rows")
    if "volume" in d:
        d["volume"] = pd.to_numeric(d["volume"], errors="coerce")
        if d.volume.isna().any() or (d.volume < 0).any():
            raise ValueError(f"{label}: invalid volume")
    return d


def align_pair(btc: pd.DataFrame, eth: pd.DataFrame) -> pd.DataFrame:
    for label, d in (("BTC", btc), ("ETH", eth)):
        if d.empty:
            raise ValueError(f"{label}: empty dataset")
        if not d.index.is_monotonic_increasing:
            raise ValueError(f"{label}: timestamps not sorted")
    x = btc.add_prefix("btc_").join(eth.add_prefix("eth_"), how="inner")
    if x.empty:
        raise ValueError("BTC/ETH have no common 15m timestamps")
    x["segment"] = (x.index.to_series().diff().ne(BAR)).cumsum().astype(int)
    x["segment"] = x["segment"].fillna(0).astype(int)
    return x


def add_regime(pair: pd.DataFrame) -> pd.DataFrame:
    """Completed 1h BTC EMA regime, visible at the 1h right-edge timestamp."""
    d = pair.copy()
    h = d[["btc_open", "btc_high", "btc_low", "btc_close"]].resample(
        "1h", label="right", closed="left"
    ).agg({"btc_open": "first", "btc_high": "max", "btc_low": "min", "btc_close": "last"})
    count = d.btc_close.resample("1h", label="right", closed="left").count()
    h = h.loc[count.reindex(h.index).eq(4)].dropna()
    h["ema50"] = h.btc_close.ewm(span=50, adjust=False, min_periods=50).mean()
    h["ema200"] = h.btc_close.ewm(span=200, adjust=False, min_periods=200).mean()
    h["regime"] = np.select(
        [h.btc_close > h.ema50, h.btc_close < h.ema50],
        ["above_ema50", "below_ema50"],
        default="range_or_unavailable",
    )
    h.loc[h.ema50.isna() | h.ema200.isna(), "regime"] = "range_or_unavailable"
    d["btc_regime_1h"] = h.regime.reindex(d.index, method="ffill")
    d["btc_regime_1h"] = d.btc_regime_1h.fillna("range_or_unavailable")
    return d


def feature_frame(pair: pd.DataFrame, beta_lookback: int, z_lookback: int) -> pd.DataFrame:
    """Rolling OLS beta/intercept and residual z-score; all baselines lagged."""
    out = pair.copy()
    out["beta"] = np.nan
    out["alpha"] = np.nan
    out["resid_mean"] = np.nan
    out["resid_std"] = np.nan
    out["z"] = np.nan
    out["corr"] = np.nan
    for _, g in pair.groupby("segment", sort=False):
        idx = g.index
        x = np.log(g.btc_close.astype(float))
        y = np.log(g.eth_close.astype(float))
        xmean = x.rolling(beta_lookback, min_periods=beta_lookback).mean().shift(1)
        ymean = y.rolling(beta_lookback, min_periods=beta_lookback).mean().shift(1)
        cov = x.rolling(beta_lookback, min_periods=beta_lookback).cov(y).shift(1)
        var = x.rolling(beta_lookback, min_periods=beta_lookback).var(ddof=1).shift(1)
        beta = cov / var.replace(0, np.nan)
        alpha = ymean - beta * xmean
        residual = y - alpha - beta * x
        rmean = residual.rolling(z_lookback, min_periods=z_lookback).mean().shift(1)
        rstd = residual.rolling(z_lookback, min_periods=z_lookback).std(ddof=1).shift(1)
        corr = x.diff().rolling(beta_lookback, min_periods=beta_lookback).corr(
            y.diff()
        ).shift(1)
        out.loc[idx, "beta"] = beta.to_numpy()
        out.loc[idx, "alpha"] = alpha.to_numpy()
        out.loc[idx, "resid_mean"] = rmean.to_numpy()
        out.loc[idx, "resid_std"] = rstd.to_numpy()
        out.loc[idx, "z"] = ((residual - rmean) / rstd.replace(0, np.nan)).to_numpy()
        out.loc[idx, "corr"] = corr.to_numpy()
    valid = (
        np.isfinite(out[["beta", "alpha", "resid_mean", "resid_std", "z", "corr"]]).all(axis=1)
        & out.beta.between(0.25, 4.0)
        & (out.resid_std > 0)
    )
    out["feature_valid"] = valid
    return out


def spread_ohlc(row: pd.Series, alpha: float, beta: float) -> tuple[float, float, float, float]:
    """Conservative synthetic log-spread OHLC for positive hedge ratios."""
    if beta <= 0:
        raise ValueError("hedge ratio must be positive")
    op = np.log(row.eth_open) - alpha - beta * np.log(row.btc_open)
    hi = np.log(row.eth_high) - alpha - beta * np.log(row.btc_low)
    lo = np.log(row.eth_low) - alpha - beta * np.log(row.btc_high)
    cl = np.log(row.eth_close) - alpha - beta * np.log(row.btc_close)
    return float(op), float(hi), float(lo), float(cl)


def check_exit(side: int, z_open: float, z_high: float, z_low: float,
               stop_z: float, target_z: float):
    """side=+1 long spread, -1 short spread; stop is always checked first."""
    if side == -1:
        if z_open >= stop_z:
            return z_open, "SL"
        if z_high >= stop_z:
            return stop_z, "SL"
        if z_low <= target_z:
            return target_z, "TP"
    else:
        if z_open <= -stop_z:
            return z_open, "SL"
        if z_low <= -stop_z:
            return -stop_z, "SL"
        if z_high >= -target_z:
            return -target_z, "TP"
    return None, None


def split_bounds(n: int):
    a, b = int(n * 0.70), int(n * 0.85)
    return {"train": (0, a), "validation": (a, b), "oos": (b, n)}


def metrics(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "profit_factor": None,
                "net_R": 0.0, "avg_R": 0.0, "max_drawdown_R": 0.0,
                "max_losing_streak": 0, "positive_month_fraction": 0.0}
    x = t.sort_values("entry_time")
    r = x.net_R.to_numpy(float)
    wins, losses = r[r > 0], r[r < 0]
    eq = np.r_[0.0, np.cumsum(r)]
    dd = eq - np.maximum.accumulate(eq)
    streak = mx = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        mx = max(mx, streak)
    monthly = x.assign(month=x.exit_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    gross_wins, gross_losses = x.loc[x.net_R > 0, "net_R"].sum(), -x.loc[x.net_R < 0, "net_R"].sum()
    return {
        "trades": len(x),
        "win_rate_pct": float((r > 0).mean() * 100),
        "profit_factor": float(gross_wins / gross_losses) if gross_losses > 0 else None,
        "net_R": float(r.sum()),
        "avg_R": float(r.mean()),
        "max_drawdown_R": float(dd.min()),
        "max_losing_streak": int(mx),
        "positive_month_fraction": float((monthly > 0).mean()) if len(monthly) else 0.0,
        "TP": int((x.outcome == "TP").sum()),
        "SL": int((x.outcome == "SL").sum()),
        "TIME": int((x.outcome == "TIME").sum()),
    }


def make_signals(f: pd.DataFrame, entry_z: float, corr_min: float,
                 direction: str) -> list[tuple[int, int]]:
    z = f.z.to_numpy(float)
    valid = f.feature_valid.to_numpy(bool)
    corr = f.corr.to_numpy(float)
    segments = f.segment.to_numpy(int)
    events = []
    for i in range(1, len(f)):
        if not (valid[i] and valid[i - 1]) or segments[i] != segments[i - 1]:
            continue
        if corr_min and corr[i] < corr_min:
            continue
        side = 0
        if z[i] >= entry_z and z[i - 1] < entry_z:
            side = -1
        elif z[i] <= -entry_z and z[i - 1] > -entry_z:
            side = 1
        if direction == "long_spread_only" and side != 1:
            continue
        if direction == "short_spread_only" and side != -1:
            continue
        if side:
            events.append((i, side))
    return events


def simulate(f: pd.DataFrame, signals: list[tuple[int, int]], split_name: str,
             bounds: dict, cfg: dict, cost_bps: int) -> pd.DataFrame:
    start_i, end_i = bounds[split_name]
    max_hold = int(cfg["max_hold"])
    rows = []
    last_exit = start_i - 1
    for sig_i, side in signals:
        entry_i = sig_i + 1
        if sig_i < start_i or entry_i <= last_exit or entry_i + max_hold > end_i:
            continue
        if f.segment.iloc[entry_i] != f.segment.iloc[sig_i]:
            continue
        if not np.all(f.segment.iloc[entry_i:entry_i + max_hold].to_numpy()
                      == f.segment.iloc[entry_i]):
            continue
        sig = f.iloc[sig_i]
        if not bool(sig.feature_valid):
            continue
        beta, alpha = float(sig.beta), float(sig.alpha)
        mu, sigma = float(sig.resid_mean), float(sig.resid_std)
        if not (0.25 <= beta <= 4.0 and sigma > 0):
            continue
        entry_row = f.iloc[entry_i]
        entry_spread = np.log(float(entry_row.eth_open)) - alpha - beta * np.log(float(entry_row.btc_open))
        entry_z = float((entry_spread - mu) / sigma)
        if side == -1 and not (entry_z >= cfg["entry_z"] and entry_z < cfg["stop_z"]):
            continue
        if side == 1 and not (entry_z <= -cfg["entry_z"] and entry_z > -cfg["stop_z"]):
            continue
        risk_z = cfg["stop_z"] - abs(entry_z)
        if risk_z <= 0:
            continue
        exit_z, outcome, exit_i = None, None, None
        for j in range(entry_i, entry_i + max_hold):
            row = f.iloc[j]
            op, hi, lo, cl = spread_ohlc(row, alpha, beta)
            zo, zh, zl = (op - mu) / sigma, (hi - mu) / sigma, (lo - mu) / sigma
            fill, why = check_exit(side, zo, zh, zl, cfg["stop_z"], cfg["target_z"])
            if why:
                exit_z, outcome, exit_i = float(fill), why, j
                break
        if exit_i is None:
            exit_i = entry_i + max_hold - 1
            row = f.iloc[exit_i]
            cl = np.log(float(row.eth_close)) - alpha - beta * np.log(float(row.btc_close))
            exit_z = float((cl - mu) / sigma)
            outcome = "TIME"
        gross_R = side * (exit_z - entry_z) / risk_z
        # Cost is charged on both legs' gross notional, expressed per gross
        # pair notional. beta is the BTC hedge notional per 1 ETH notional.
        cost_R = (cost_bps / 10000.0) * (1.0 + beta) / (risk_z * sigma)
        net_R = gross_R - cost_R
        rows.append({
            "split": split_name, "entry_time": f.index[entry_i],
            "signal_time": f.index[sig_i], "exit_time": f.index[exit_i],
            "side": "long_spread" if side == 1 else "short_spread",
            "beta": beta, "entry_z": entry_z, "exit_z": exit_z,
            "entry_btc": float(f.btc_open.iloc[entry_i]),
            "entry_eth": float(f.eth_open.iloc[entry_i]),
            "exit_btc": float(f.btc_close.iloc[exit_i]),
            "exit_eth": float(f.eth_close.iloc[exit_i]),
            "outcome": outcome, "gross_R": gross_R, "cost_R": cost_R,
            "net_R": net_R, "cost_bps_per_leg_round_trip": cost_bps,
            "btc_regime_1h": str(f.btc_regime_1h.iloc[entry_i]),
            "hold_bars": exit_i - entry_i + 1,
            **cfg,
        })
        last_exit = exit_i
    return pd.DataFrame(rows)


def run(btc_path: Path, eth_path: Path, out: Path):
    btc, eth = load_ohlcv(btc_path, "BTC"), load_ohlcv(eth_path, "ETH")
    pair = align_pair(btc, eth)
    pair = add_regime(pair)
    bounds = split_bounds(len(pair))
    beta_windows = sorted(set(BETA_LOOKBACKS))
    z_windows = sorted(set(Z_LOOKBACKS))
    feature_cache = {}
    for bw, zw in itertools.product(beta_windows, z_windows):
        feature_cache[(bw, zw)] = feature_frame(pair, bw, zw)

    configs = []
    for vals in itertools.product(BETA_LOOKBACKS, Z_LOOKBACKS, ENTRY_ZS, STOP_ZS,
                                  TARGET_ZS, MAX_HOLDS, DIRECTIONS, CORR_FILTERS):
        bw, zw, ez, sz, tz, hold, direction, corr = vals
        configs.append({
            "beta_lookback": bw, "z_lookback": zw, "entry_z": ez,
            "stop_z": sz, "target_z": tz, "max_hold": hold,
            "direction": direction, "corr_min": corr,
        })

    matrix, cost_rows = [], []
    for cfg in configs:
        f = feature_cache[(cfg["beta_lookback"], cfg["z_lookback"])]
        signals = make_signals(f, cfg["entry_z"], cfg["corr_min"], cfg["direction"])
        tr = simulate(f, signals, "train", bounds, cfg, 12)
        va = simulate(f, signals, "validation", bounds, cfg, 12)
        tm, vm = metrics(tr), metrics(va)
        row = dict(cfg)
        row.update({f"train_{k}": v for k, v in tm.items()})
        row.update({f"validation_{k}": v for k, v in vm.items()})
        train_gate = (
            tm["trades"] >= MIN_TRAIN and tm.get("profit_factor") is not None
            and tm["profit_factor"] >= 1.05 and tm["net_R"] > 0
            and tm["positive_month_fraction"] >= 0.50 and tm["max_drawdown_R"] >= -20
        )
        validation_gate = (
            vm["trades"] >= MIN_VALIDATION and vm.get("profit_factor") is not None
            and vm["profit_factor"] >= 1.05 and vm["net_R"] > 0
            and vm["positive_month_fraction"] >= 0.50 and vm["max_drawdown_R"] >= -12
        )
        row["train_gate"] = bool(train_gate)
        row["validation_gate"] = bool(train_gate and validation_gate)
        matrix.append(row)
        if train_gate:
            for sp in ("train", "validation"):
                for cost in COSTS:
                    t = simulate(f, signals, sp, bounds, cfg, cost)
                    cost_rows.append({**cfg, "split": sp, "cost_bps_per_leg_round_trip": cost,
                                      **metrics(t)})

    md = pd.DataFrame(matrix)
    out.mkdir(parents=True, exist_ok=True)
    md.to_csv(out / "matrix.csv", index=False)

    diagnostics, monthly, regimes = [], [], []
    specs = []
    train_candidates = md[md.train_gate].sort_values(
        ["train_profit_factor", "train_positive_month_fraction", "train_max_drawdown_R", "train_net_R"],
        ascending=[False, False, False, False],
    )
    if not train_candidates.empty:
        specs.append(("best_train_candidate", train_candidates.iloc[0]))
    val_candidates = md[md.validation_trades >= MIN_VALIDATION].sort_values(
        ["validation_profit_factor", "validation_net_R"], ascending=[False, False],
    )
    if not val_candidates.empty:
        specs.append(("best_validation_candidate_min20", val_candidates.iloc[0]))

    for label, selected in specs:
        cfg = {k: selected[k] for k in configs[0]}
        f = feature_cache[(cfg["beta_lookback"], cfg["z_lookback"])]
        signals = make_signals(f, cfg["entry_z"], cfg["corr_min"], cfg["direction"])
        for sp in ("train", "validation"):
            t = simulate(f, signals, sp, bounds, cfg, 12)
            if t.empty:
                continue
            t["diagnostic_label"] = label
            diagnostics.append(t)
            mm = t.assign(month=t.exit_time.dt.strftime("%Y-%m")).groupby("month").net_R.agg(
                ["count", "sum", "mean"]
            ).reset_index()
            for item in mm.to_dict("records"):
                monthly.append({"candidate": label, "split": sp, **item})
            rg = t.groupby("btc_regime_1h").net_R.agg(["count", "sum", "mean"]).reset_index()
            for item in rg.to_dict("records"):
                regimes.append({"candidate": label, "split": sp, **item})

    if diagnostics:
        pd.concat(diagnostics, ignore_index=True).to_csv(out / "diagnostic_trades_12bp.csv", index=False)
    pd.DataFrame(monthly).to_csv(out / "diagnostic_monthly.csv", index=False)
    pd.DataFrame(regimes).to_csv(out / "diagnostic_regimes.csv", index=False)

    passes = md[md.validation_gate].copy()
    selected_cfg = None
    if not passes.empty:
        passes = passes.sort_values(
            ["validation_profit_factor", "validation_positive_month_fraction",
             "validation_max_drawdown_R", "validation_net_R"],
            ascending=[False, False, False, False],
        )
        selected_cfg = {k: passes.iloc[0][k] for k in configs[0]}
        f = feature_cache[(selected_cfg["beta_lookback"], selected_cfg["z_lookback"])]
        signals = make_signals(f, selected_cfg["entry_z"], selected_cfg["corr_min"],
                               selected_cfg["direction"])
        for cost in COSTS:
            t = simulate(f, signals, "oos", bounds, selected_cfg, cost)
            cost_rows.append({**selected_cfg, "split": "oos",
                              "cost_bps_per_leg_round_trip": cost, **metrics(t)})

    pd.DataFrame(cost_rows).to_csv(out / "cost_sensitivity.csv", index=False)
    aligned = pair.index
    meta = {
        "classification": "experimental pair-trading backtest; no live use",
        "btc_rows": len(btc), "eth_rows": len(eth), "aligned_rows": len(pair),
        "btc_sha256": file_sha256(btc_path), "eth_sha256": file_sha256(eth_path),
        "start_utc": aligned.min().isoformat(), "end_utc": aligned.max().isoformat(),
        "btc_gap_count": int((btc.index.to_series().diff().dropna() != BAR).sum()),
        "eth_gap_count": int((eth.index.to_series().diff().dropna() != BAR).sum()),
        "aligned_gap_count": int((pair.index.to_series().diff().dropna() != BAR).sum()),
        "btc_zero_volume": int((btc.volume == 0).sum()) if "volume" in btc else None,
        "eth_zero_volume": int((eth.volume == 0).sum()) if "volume" in eth else None,
        "train_end_utc": pair.index[bounds["train"][1]].isoformat(),
        "validation_end_utc": pair.index[bounds["validation"][1]].isoformat(),
        "split": "chronological 70/15/15 by aligned 15m row index",
        "configurations": len(configs),
        "training_eligible": int(md.train_gate.sum()),
        "validation_passes": int(md.validation_gate.sum()),
        "oos_evaluated": selected_cfg is not None,
        "selected_config": selected_cfg,
        "signal": "cross of completed 15m residual z beyond +/-1.5/2.0/2.5; rolling OLS log(ETH) on log(BTC) uses prior 10d/30d only; residual mean/std uses prior 3d/7d only",
        "entry_exit": "next 15m open for both legs; freeze signal-time alpha/beta/mean/std; stop z 3.5/4.0; target z 0/0.5; max hold 24h/48h; one pair position at a time/config",
        "hedge_ratio": "positive beta only, constrained to 0.25-4.0; 1 ETH notional versus beta BTC notional",
        "costs": "6/12/20bp assumed round-trip per leg; 12bp per leg primary; funding, borrow, separate spread and market impact excluded",
        "execution": "synthetic log-spread OHLC uses adverse cross-leg extremes; stop checked before target; adverse stop gaps at observed open; target at target; timeout at final close",
        "selection_gates": "train >=40 trades, PF>=1.05, net R>0, positive months>=50%, DD>=-20R; validation >=20 trades, PF>=1.05, net R>0, positive months>=50%, DD>=-12R; OOS only after one validation pass",
        "limitations": [
            "Rolling residual mean-reversion is a statistical hypothesis, not proof of cointegration or stationarity.",
            "Funding/borrow and contract-specific settlement cashflows are excluded; 24h/48h holding results are diagnostic and cannot be promoted without them.",
            "Costs are assumed per leg round-trip and actual account fee tier/spread are not verified.",
            "Synthetic spread OHLC is conservative but cannot reconstruct exact intrabar ordering between two independently traded legs."
        ],
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    print(json.dumps(meta, indent=2, default=str))
    print("\nTRAIN-ELIGIBLE")
    print(md[md.train_gate].to_string(index=False) if md.train_gate.any() else "none")
    print("\nVALIDATION PASSES")
    print(md[md.validation_gate].to_string(index=False) if md.validation_gate.any() else "none")


def self_test():
    # Positive beta synthetic spread extremes.
    row = pd.Series({
        "btc_open": 50.0, "btc_high": 60.0, "btc_low": 40.0, "btc_close": 55.0,
        "eth_open": 100.0, "eth_high": 110.0, "eth_low": 90.0, "eth_close": 105.0,
    })
    op, hi, lo, cl = spread_ohlc(row, 0.0, 1.0)
    assert np.isclose(op, np.log(2.0))
    assert np.isclose(hi, np.log(110.0 / 40.0))
    assert np.isclose(lo, np.log(90.0 / 60.0))
    assert np.isclose(cl, np.log(105.0 / 55.0))
    # Stop-first when both stop and target are touched.
    assert check_exit(-1, 2.0, 4.0, -1.0, 3.5, 0.0) == (3.5, "SL")
    assert check_exit(1, -2.0, 1.0, -4.0, 3.5, 0.0) == (-3.5, "SL")
    # Adverse stop gaps fill at the observed open, not the stop threshold.
    assert check_exit(-1, 3.8, 4.0, 3.6, 3.5, 0.0) == (3.8, "SL")
    assert check_exit(1, -3.8, -3.6, -4.0, 3.5, 0.0) == (-3.8, "SL")
    # Future perturbations cannot alter earlier rolling beta/z features.
    rng = np.random.default_rng(7)
    n = 420
    idx = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    bx = 10.0 + np.cumsum(rng.normal(0, 0.002, n))
    ex = 8.0 + 1.1 * (bx - 10.0) + np.cumsum(rng.normal(0, 0.001, n))
    def make_frame(b, e):
        return pd.DataFrame({
            "btc_open": np.exp(b), "btc_high": np.exp(b + 0.002),
            "btc_low": np.exp(b - 0.002), "btc_close": np.exp(b),
            "eth_open": np.exp(e), "eth_high": np.exp(e + 0.002),
            "eth_low": np.exp(e - 0.002), "eth_close": np.exp(e),
            "segment": np.zeros(n, dtype=int),
        }, index=idx)
    base = make_frame(bx, ex)
    altered_bx, altered_ex = bx.copy(), ex.copy()
    altered_bx[320:] += np.linspace(0.2, 0.8, n - 320)
    altered_ex[320:] -= np.linspace(0.1, 0.4, n - 320)
    changed = make_frame(altered_bx, altered_ex)
    f1 = feature_frame(base, 48, 24)
    f2 = feature_frame(changed, 48, 24)
    for col in ("beta", "alpha", "resid_mean", "resid_std", "z", "corr"):
        assert np.allclose(f1[col].iloc[:320], f2[col].iloc[:320], equal_nan=True)
    # A gap starts a fresh segment; features must not bridge it.
    gap = base.drop(index=idx[250:255]).copy()
    gap["segment"] = (gap.index.to_series().diff().ne(BAR)).cumsum().astype(int)
    fg = feature_frame(gap, 48, 24)
    after = gap.index.get_loc(idx[255])
    assert pd.isna(fg.z.iloc[after])
    assert fg.segment.iloc[after] != fg.segment.iloc[after - 1]
    print("7 pair causality, gap, spread-OHLC and execution self-tests passed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--btc-csv", type=Path)
    p.add_argument("--eth-csv", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("results/btc-eth-pairs"))
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    if not a.btc_csv or not a.eth_csv:
        p.error("provide --btc-csv and --eth-csv")
    run(a.btc_csv, a.eth_csv, a.output_dir)


if __name__ == "__main__":
    main()
