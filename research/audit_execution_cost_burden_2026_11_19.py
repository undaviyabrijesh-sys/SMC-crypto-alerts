#!/usr/bin/env python3
"""Reproduce the 2026-11-19 cross-family execution-cost burden audit.

This is a retrospective accounting audit, not a strategy backtest.
It selects one representative configuration per split-based family using
DEVELOPMENT net_R at 10 bps only, then evaluates that exact configuration
in validation. Validation is never used for selection.
"""
from __future__ import annotations
import argparse, io, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

COSTS = [0, 4, 7, 10, 20]

def read_member(zip_path: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        return pd.read_csv(io.BytesIO(zf.read(member)))

def pf(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    pos = float(x[x > 0].sum())
    neg = float(-x[x < 0].sum())
    if neg > 0:
        return pos / neg
    return float("inf") if pos > 0 else 0.0

def stats_for(g: pd.DataFrame, risk_col: str, entry_col: str, gross_col: str,
              cost_bps: int, published_net_col: str | None = None) -> dict:
    risk = g[risk_col].to_numpy(float)
    entry = g[entry_col].to_numpy(float)
    gross = g[gross_col].to_numpy(float)
    risk_bps = risk / entry * 10_000.0
    if np.any(~np.isfinite(risk_bps)) or np.any(risk_bps <= 0):
        raise ValueError("Invalid stop-risk basis points")
    cost_r = cost_bps / risk_bps
    net = gross - cost_r
    discrepancy = None
    if published_net_col:
        published = g[published_net_col].to_numpy(float)
        discrepancy = float(np.max(np.abs(net - published))) if len(g) else 0.0
        if discrepancy > 1e-9:
            raise AssertionError(f"Published net-R mismatch: {discrepancy}")
    return {
        "trades": int(len(g)),
        "cost_bps": int(cost_bps),
        "gross_win_pct": float((gross > 0).mean() * 100),
        "gross_pf": pf(gross),
        "gross_mean_R": float(gross.mean()),
        "gross_sum_R": float(gross.sum()),
        "net_win_pct": float((net > 0).mean() * 100),
        "net_pf": pf(net),
        "net_mean_R": float(net.mean()),
        "net_sum_R": float(net.sum()),
        "median_stop_risk_bps": float(np.median(risk_bps)),
        "p10_stop_risk_bps": float(np.quantile(risk_bps, .10)),
        "p90_stop_risk_bps": float(np.quantile(risk_bps, .90)),
        "median_cost_R": float(np.median(cost_r)),
        "p90_cost_R": float(np.quantile(cost_r, .90)),
        "share_cost_gt_0_25R_pct": float((cost_r > .25).mean() * 100),
        "share_cost_gt_0_50R_pct": float((cost_r > .50).mean() * 100),
        "share_cost_gt_1R_pct": float((cost_r > 1.0).mean() * 100),
        "published_net_max_abs_diff": discrepancy,
    }

def select_dev_config(summary: pd.DataFrame, split_col: str, config_col: str,
                      net_col: str, cost_col: str = "cost_bps") -> str:
    d = summary[(summary[split_col] == "development") & (summary[cost_col] == 10)].copy()
    d = d[d[net_col].notna()].sort_values([net_col, config_col], ascending=[False, True])
    if d.empty:
        raise ValueError("No development rows at 10 bps")
    return str(d.iloc[0][config_col])

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, default=Path("inputs"))
    ap.add_argument("--output-dir", type=Path, default=Path("results"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    z = {p.stem: p for p in args.input_dir.glob("*.zip")}
    required = [
        "btc_5m_crt_previous_hour_sweep_reclaim_2026-11-19",
        "btc_1h_ema_crossover_funding_safe_research_2026-11-18",
        "btc_donchian_breakout_research_2026-11-18",
        "btc_rsi2_mean_reversion_research_2026-11-18",
        "true_vp_sweep_delta_execution_pilot_2026-11-18",
    ]
    missing = [x for x in required if x not in z]
    if missing:
        raise FileNotFoundError(f"Missing input ZIPs: {missing}")

    selected = []
    output_rows = []

    # CRT: choose the highest development net-R configuration at 10 bps.
    p = z[required[0]]
    sm = read_member(p, "results/summary_dev_val_costs.csv")
    cfg = select_dev_config(sm, "split", "variant", "net_R")
    tr = read_member(p, "results/trades_dev_val.csv")
    gcfg = tr[tr.variant == cfg]
    selected.append({"family":"BTC 5m CRT-style","config":cfg,"selection":"highest development net_R at 10 bps"})
    for split,g in gcfg.groupby("split"):
        for c in COSTS:
            output_rows.append({"family":"BTC 5m CRT-style","configuration":cfg,"split":split,
                                **stats_for(g,"risk_points","entry","gross_R",c)})

    # EMA crossover: select by development only; verify published per-trade net R.
    p = z[required[1]]
    sm = read_member(p, "ema_cross_research/results/summary_dev_val_costs.csv")
    cfg = select_dev_config(sm, "sample", "config_id", "net_R")
    tr = read_member(p, "ema_cross_research/results/trades_dev_val_10bps.csv")
    gcfg = tr[tr.config_id == cfg]
    selected.append({"family":"BTC 1h EMA crossover","config":cfg,"selection":"highest development net_R at 10 bps"})
    for split,g in gcfg.groupby("sample"):
        for c in COSTS:
            published = {10:"net_R_10bp",4:"net_R_4bp",7:"net_R_7bp",20:"net_R_20bp"}.get(c)
            output_rows.append({"family":"BTC 1h EMA crossover","configuration":cfg,"split":split,
                                **stats_for(g,"risk","entry","gross_R",c,published)})

    # Donchian: development-ranked only; never select using validation.
    p = z[required[2]]
    sm = read_member(p, "donchian_package/results/summary_primary_10bps.csv")
    cfg = select_dev_config(sm, "split", "config", "net_r")
    tr = read_member(p, "donchian_package/results/trades_dev_val.csv")
    gcfg = tr[tr.config == cfg]
    selected.append({"family":"BTC 15m Donchian breakout","config":cfg,"selection":"highest development net_r at 10 bps"})
    for split,g in gcfg.groupby("split"):
        for c in COSTS:
            gg = g[g.cost_bps == 10].copy()
            if gg.empty:
                raise ValueError("Donchian trade ledger lacks 10 bps rows")
            output_rows.append({"family":"BTC 15m Donchian breakout","configuration":cfg,"split":split,
                                **stats_for(gg,"risk_abs","entry","gross_r",c,
                                            "net_r" if c == 10 else None)})

    # RSI(2): development-ranked only; verify published net R at 10 bps.
    p = z[required[3]]
    sm = read_member(p, "package/results/summary_dev_val_costs.csv")
    cfg = select_dev_config(sm, "split", "config", "net_r")
    tr = read_member(p, "package/results/trades_dev_val_10bps.csv")
    gcfg = tr[tr.config == cfg]
    selected.append({"family":"BTC 15m RSI(2) extreme entry","config":cfg,"selection":"highest development net_r at 10 bps"})
    for split,g in gcfg.groupby("split"):
        for c in COSTS:
            output_rows.append({"family":"BTC 15m RSI(2) extreme entry","configuration":cfg,"split":split,
                                **stats_for(g,"risk_abs","entry","gross_r",c,
                                            "net_r" if c == 10 else None)})

    # True VP: September post-hoc diagnostic only. Include both variants without selection.
    p = z[required[4]]
    tr = read_member(p, "true_vp_sweep_delta/results/trades.csv")
    for variant,g_variant in tr.groupby("variant"):
        selected.append({"family":"BTCUSDT true VP sweep/reclaim","config":variant,
                         "selection":"include both frozen variants; one-month post-hoc diagnostic"})
        for c in COSTS:
            g = g_variant[g_variant.cost_bps == c].copy()
            output_rows.append({"family":"BTCUSDT true VP sweep/reclaim","configuration":variant,
                                "split":"September post-hoc diagnostic",
                                **stats_for(g,"risk","entry","gross_R",c,"net_R")})

    out = pd.DataFrame(output_rows)
    out.to_csv(args.output_dir/"execution_cost_burden_metrics.csv", index=False)
    (args.output_dir/"selected_configurations.json").write_text(json.dumps(selected,indent=2)+"\n")
    meta = {
        "status":"PASS",
        "configuration_rows":len(selected),
        "metric_rows":len(out),
        "costs_bps":COSTS,
        "selection_policy":"development-ranked at 10 bps for split-based families; same configuration carried into validation; validation never used for selection",
        "cost_formula":"cost_R = cost_bps / (abs(entry-stop)/entry*10000); net_R = gross_R - cost_R",
        "limitations":[
            "Retrospective accounting audit, not a new strategy backtest.",
            "Flat round-trip bps costs do not model maker/taker asymmetry, spread, market impact, funding or queue position.",
            "The true VP rows are one-month September 2026 post-hoc diagnostics, not chronological validation.",
            "Selected rows are representative development-ranked diagnostics, not promotion candidates.",
            "R-based cost burden is sensitive to initial stop distance and does not imply that widening stops preserves the original strategy."
        ]
    }
    (args.output_dir/"audit_metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps(meta,indent=2))
    print(out[out.cost_bps == 10][["family","configuration","split","trades","gross_mean_R",
        "median_stop_risk_bps","median_cost_R","p90_cost_R","share_cost_gt_0_50R_pct",
        "share_cost_gt_1R_pct","net_mean_R","net_pf"]].round(3).to_string(index=False))

if __name__ == "__main__":
    main()
