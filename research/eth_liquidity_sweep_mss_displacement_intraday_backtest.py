"""ETHUSD 15m liquidity-sweep + MSS + displacement, with BTC 4h confirmation research.

Builds on the causal sweep/MSS event engine. A candidate is retained only if
its first MSS candle has a directionally aligned body >= the configured ATR
threshold, and optionally closes in the outer quartile of its candle range.
The displacement candle is known closed before next-bar-open entry.

Research only; no live signals or execution.
"""
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import liquidity_sweep_mss_intraday_backtest as base
import crt_backtest as fetcher

OUT = Path("eth_liquidity_displacement_results")
OUT.mkdir(exist_ok=True)
COSTS = (6, 12, 20)
EXTERNAL_STRENGTHS = (2, 3)
LOCAL_STRENGTHS = (2, 3)
MSS_WAITS = (4, 8)
STOP_BUFFERS = (0.0, 0.1)
TARGETS = (1.5, 2.0, 3.0)
DISPLACEMENT_MODES = (
    ("none", 0.0, False),
    ("body_0.5_atr", 0.5, False),
    ("body_0.75_atr", 0.75, False),
    ("body_0.5_atr_close_quartile", 0.5, True),
    ("body_0.75_atr_close_quartile", 0.75, True),
)
HTF_FILTERS = ("none", "eth_ema50_200", "btc_ema50_200")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
MIN_TRAIN = 40
MIN_VALIDATION = 20
MAX_SHORTLIST = 25


def displacement_ok(d, event, mode):
    name, min_body_atr, require_close_quartile = mode
    if name == "none":
        return True
    i = event["mss_i"]
    o = float(d.open.iloc[i])
    h = float(d.high.iloc[i])
    l = float(d.low.iloc[i])
    c = float(d.close.iloc[i])
    atr = float(d.atr14.iloc[i])
    if not np.isfinite([o, h, l, c, atr]).all() or atr <= 0 or h <= l:
        return False
    side = event["side"]
    directional_body = (c - o) if side == "long" else (o - c)
    if directional_body <= 0 or directional_body / atr < min_body_atr:
        return False
    if require_close_quartile:
        close_location = (c - l) / (h - l)
        if side == "long" and close_location < 0.75:
            return False
        if side == "short" and close_location > 0.25:
            return False
    return True



def attach_btc_context(eth_d, btc_d):
    """Attach only completed BTC 4h context; expire it across BTC data gaps."""
    btc_h4 = base.complete_resample(btc_d, "4h", 16)
    if btc_h4.empty:
        raise RuntimeError("No complete BTC 4h candles available for confirmation")
    source_segment = btc_d.segment.resample(
        "4h", label="right", closed="left"
    ).first()
    btc_h4["source_segment"] = source_segment.reindex(btc_h4.index)
    btc_h4["segment"] = btc_h4.index.to_series().diff().ne(
        pd.Timedelta("4h")
    ).cumsum()
    btc_h4["ema50_close"] = btc_h4.groupby("segment").close.transform(
        lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean()
    )
    btc_h4["ema200_close"] = btc_h4.groupby("segment").close.transform(
        lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean()
    )
    bull = (
        (btc_h4.close > btc_h4.ema50_close)
        & (btc_h4.ema50_close > btc_h4.ema200_close)
    )
    bear = (
        (btc_h4.close < btc_h4.ema50_close)
        & (btc_h4.ema50_close < btc_h4.ema200_close)
    )
    btc_h4["regime"] = np.select(
        [bull, bear], ["bull", "bear"], default="mixed_or_unavailable"
    )

    ctx = btc_h4.reindex(eth_d.index, method="ffill")
    h4_stamp = pd.Series(btc_h4.index, index=btc_h4.index).reindex(
        eth_d.index, method="ffill"
    )
    source_seg_at_entry = btc_h4.source_segment.reindex(
        eth_d.index, method="ffill"
    )
    current_seg_at_entry = btc_d.segment.reindex(
        eth_d.index, method="ffill"
    )
    btc_bar_stamp = pd.Series(btc_d.index, index=btc_d.index).reindex(
        eth_d.index, method="ffill"
    )
    now = pd.Series(eth_d.index, index=eth_d.index)
    age_15m = now - btc_bar_stamp
    age_4h = now - h4_stamp
    fresh = (
        age_15m.le(base.BAR)
        & age_4h.le(pd.Timedelta("6h"))
        & source_seg_at_entry.eq(current_seg_at_entry)
        & h4_stamp.notna()
    )

    out = eth_d.copy()
    out["btc_h4_close"] = ctx.close.where(fresh)
    out["btc_h4_ema50_close"] = ctx.ema50_close.where(fresh)
    out["btc_h4_ema200_close"] = ctx.ema200_close.where(fresh)
    out["btc_h4_time"] = h4_stamp.where(fresh)
    out["btc_h4_age_minutes"] = age_4h.dt.total_seconds() / 60.0
    out["btc_regime"] = ctx.regime.where(fresh, "mixed_or_unavailable")
    return out, btc_h4


def simulate_asset(d, events, cfg, start_i, end_i):
    """Use ETH 4h or causally completed BTC 4h EMA context as preregistered."""
    label = cfg["htf_filter"]
    if label == "none":
        rows = base.simulate(d, events, cfg, start_i, end_i)
    elif label == "eth_ema50_200":
        local_cfg = dict(cfg, htf_filter="ema50_200")
        rows = base.simulate(d, events, local_cfg, start_i, end_i)
    elif label == "btc_ema50_200":
        temp = d.copy()
        temp["h4_close"] = temp["btc_h4_close"]
        temp["h4_ema50_close"] = temp["btc_h4_ema50_close"]
        temp["h4_ema200_close"] = temp["btc_h4_ema200_close"]
        temp["regime"] = temp["btc_regime"]
        local_cfg = dict(cfg, htf_filter="ema50_200")
        rows = base.simulate(temp, events, local_cfg, start_i, end_i)
    else:
        raise ValueError(f"Unknown HTF filter: {label}")

    for row in rows:
        row["config_id"] = cfg["config_id"]
        row["htf_filter"] = label
        row["eth_regime"] = d.loc[row["entry_time"], "regime"]
        row["btc_regime"] = d.loc[row["entry_time"], "btc_regime"]
        row["btc_h4_time"] = d.loc[row["entry_time"], "btc_h4_time"]
        row["btc_h4_age_minutes"] = d.loc[row["entry_time"], "btc_h4_age_minutes"]
        row["regime"] = row["eth_regime"]
    return rows

def main():
    fetcher.SYMBOL = "ETHUSD"
    fetcher.OUT = Path("eth_liquidity_source_data")
    fetcher.OUT.mkdir(exist_ok=True)
    eth_raw = fetcher.fetch("15m")
    d, h1 = base.prepare(eth_raw)
    eth_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    fetcher.SYMBOL = "BTCUSD"
    fetcher.OUT = Path("btc_context_source_data")
    fetcher.OUT.mkdir(exist_ok=True)
    btc_raw = fetcher.fetch("15m")
    btc_d, _ = base.prepare(btc_raw)
    btc_hash = hashlib.sha256(btc_d.to_csv().encode()).hexdigest()
    btc_gaps = int((btc_d.index.to_series().diff().dropna() != base.BAR).sum())

    d, btc_h4 = attach_btc_context(d, btc_d)
    if len(d) < 10000 or len(h1) < 1000 or len(btc_h4) < 200:
        raise RuntimeError(
            f"Insufficient data: ETH 15m={len(d)}, ETH 1h={len(h1)}, "
            f"BTC 4h={len(btc_h4)}"
        )
    n = len(d)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    samples = (("train", 0, train_end), ("validation", train_end, val_end))
    gaps = int((d.index.to_series().diff().dropna() != base.BAR).sum())
    dataset_hash = hashlib.sha256(d.to_csv().encode()).hexdigest()

    event_cache = {}
    for ext_s, loc_s, wait in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS
    ):
        event_cache[(ext_s, loc_s, wait)] = base.build_events(
            d, h1, ext_s, loc_s, wait
        )

    configs = []
    for values in itertools.product(
        EXTERNAL_STRENGTHS, LOCAL_STRENGTHS, MSS_WAITS, STOP_BUFFERS,
        TARGETS, DISPLACEMENT_MODES, HTF_FILTERS, DIRECTIONS, SESSIONS
    ):
        ext_s, loc_s, wait, sb, target, mode, htf, direction, session = values
        mode_name = mode[0]
        cfg_id = (
            f"h1p{ext_s}_mss{loc_s}_wait{wait}_buf{sb}_{target}R_"
            f"{mode_name}_{htf}_{direction}_{session}"
        )
        configs.append(dict(
            config_id=cfg_id, external_strength=ext_s, local_strength=loc_s,
            mss_wait=wait, stop_buffer=sb, target_r=target,
            displacement_mode=mode_name, htf_filter=htf,
            direction=direction, session=session,
        ))

    trade_rows, summary_rows, monthly_rows, regime_rows = [], [], [], []
    event_counts = {}
    mode_map = {x[0]: x for x in DISPLACEMENT_MODES}
    for cfg in configs:
        key = (cfg["external_strength"], cfg["local_strength"], cfg["mss_wait"])
        events = event_cache[key]
        filtered = [e for e in events if displacement_ok(d, e, mode_map[cfg["displacement_mode"]])]
        event_counts[cfg["displacement_mode"]] = len(filtered)
        for sample, start, end in samples:
            local = dict(cfg, sample=sample)
            rows = simulate_asset(d, filtered, local, start, end)
            if rows:
                trade_rows.extend(rows)
            g = pd.DataFrame(rows)
            for bps in COSTS:
                summary_rows.append(dict(**local, cost_bps=bps, **base.trade_metrics(g, bps)))
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
            "stop_buffer", "target_r", "displacement_mode", "htf_filter",
            "direction", "session"
        ]].to_dict(), sample="oos")
        oos_events = event_cache[(
            oos_cfg["external_strength"], oos_cfg["local_strength"], oos_cfg["mss_wait"]
        )]
        oos_events = [
            e for e in oos_events
            if displacement_ok(d, e, mode_map[oos_cfg["displacement_mode"]])
        ]
        oos_rows = simulate_asset(d, oos_events, oos_cfg, val_end, n)
        if oos_rows:
            trades = pd.concat([trades, pd.DataFrame(oos_rows)], ignore_index=True)
            pd.DataFrame(oos_rows).to_csv(OUT / "selected_oos_trades.csv", index=False)
            oos_metrics = base.trade_metrics(pd.DataFrame(oos_rows), 12)
            oos_note = "One pre-selected validation-passing candidate evaluated once on OOS. " + json.dumps(oos_metrics)
        else:
            oos_note = "A candidate passed selection, but no eligible OOS trades were generated."
        trades.to_csv(OUT / "trades.csv", index=False)

    metadata = {
        "symbol": "ETHUSD",
        "timeframe": "ETH 15m execution; confirmed ETH 1h liquidity levels; completed ETH or BTC 4h EMA context",
        "rows_15m": len(d), "rows_1h_complete": len(h1),
        "start_utc": str(d.index.min()), "end_utc": str(d.index.max()),
        "gaps_15m": gaps, "dataset_sha256": dataset_hash,
        "eth_dataset_sha256": eth_hash,
        "btc_dataset_sha256": btc_hash,
        "btc_rows_15m": len(btc_d), "btc_gaps_15m": btc_gaps,
        "btc_rows_4h_complete": len(btc_h4),
        "btc_context_rule": "Completed 4h BTC bars only; context expires after 6h and is invalidated across BTC 15m segment gaps; exact/as-of 15m BTC bar age must be <=15m",
        "train_end_utc": str(d.index[train_end - 1]),
        "validation_end_utc": str(d.index[val_end - 1]),
        "oos_start_utc": str(d.index[val_end]),
        "matrix_configurations": len(configs),
        "event_counts_by_displacement_mode": event_counts,
        "train_eligible": len(eligible), "shortlisted": len(shortlist),
        "validation_pass": len(passed),
        "selected_oos_config": None if selected is None else selected.config_id,
        "oos_evaluated": bool(passed),
        "displacement_rules": {
            "none": "No displacement requirement",
            "body_0.5_atr": "Directional MSS candle body >= 0.5 x ATR14 at MSS close",
            "body_0.75_atr": "Directional MSS candle body >= 0.75 x ATR14 at MSS close",
            "body_0.5_atr_close_quartile": "Directional body >= 0.5 x ATR14 and close in directional outer quartile",
            "body_0.75_atr_close_quartile": "Directional body >= 0.75 x ATR14 and close in directional outer quartile",
            "timing": "MSS candle is fully closed before next-15m-open entry; first MSS only, a weak first MSS rejects the event rather than waiting for a later break"
        },
        "cost_sensitivity_bps": list(COSTS),
        "cost_assumption": "6/12/20bp round-trip; no funding or separate spread/slippage",
        "split": "chronological 70/15/15; training eligibility then top-25 shortlist then validation; untouched OOS evaluated once only if one candidate passes both gates",
        "selection": {
            "train": ">=40 trades, net_R>0, PF>=1.05, max DD no worse than -25R",
            "validation": ">=20 trades, net_R>0, PF>=1.05, max DD no worse than -15R, >=50% positive active months",
            "shortlist": "top 25 by train net_R/(abs(max_drawdown_R)+1)"
        },
        "limitations": "12bp primary cost assumed, not user fee-tier verified; no funding or separate spread/slippage; 07-19 UTC fixed session proxy; mechanical pivot/MSS/displacement definitions are not discretionary SMC; BTC context uses only completed 4h candles, expires after 6h and is invalidated across 15m data gaps; one trade at a time per configuration and 8h maximum hold"
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
    print(f"Artifacts: {OUT}/summary.csv, trades.csv, monthly_summary.csv, regime_summary.csv, methodology.json; BTC context source hashes are recorded in metadata")


if __name__ == "__main__":
    main()
