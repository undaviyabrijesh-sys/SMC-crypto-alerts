#!/usr/bin/env python3
"""Preregistered BTC Asia-range sweep fade conditioned on completed 4h trend.

Imports the base event definition and Delta BTCUSD 5m downloader. The only
filter is a completed 4h EMA50/EMA200 trend alignment. Controls match UTC day,
side and 4h regime, using non-sweep bars outside a +/-30m signal neighbourhood.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

from btc_session_range_sweep_event_study import (
    COSTS_BPS, HORIZONS, STEP, StudyError, _is_sweep, detect_events,
    evaluate, fetch_data,
)

SEED = 20261114
EXCLUSION_BARS = 6
FOUR_HOURS = pd.Timedelta(hours=4)
BARS_4H = 48

def completed_4h_regime(data: pd.DataFrame) -> pd.Series:
    """Return only regimes from complete 48-bar 4h candles, available at close."""
    x = data.copy()
    grouped = x[["open","high","low","close"]].resample(
        "4h",label="right",closed="left"
    ).agg({"open":"first","high":"max","low":"min","close":"last"})
    counts = x.close.resample("4h",label="right",closed="left").count()
    segments = x.segment.resample("4h",label="right",closed="left").nunique()
    h4 = grouped.loc[counts.eq(BARS_4H) & segments.eq(1)].dropna()
    if h4.empty:
        raise StudyError("No complete 4h bars available for trend calculation")
    h4["segment"] = h4.index.to_series().diff().ne(FOUR_HOURS).cumsum().to_numpy()
    h4["ema50"] = h4.groupby("segment").close.transform(
        lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean()
    )
    h4["ema200"] = h4.groupby("segment").close.transform(
        lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean()
    )
    bull = (h4.close > h4.ema50) & (h4.ema50 > h4.ema200)
    bear = (h4.close < h4.ema50) & (h4.ema50 < h4.ema200)
    h4["regime"] = np.select([bull,bear],["bull","bear"],default="neutral")
    # The 4h rows are right-labelled at their close; forward-fill only after that time.
    mapped = h4.regime.reindex(data.index,method="ffill")
    return mapped.fillna("unavailable").rename("htf_regime")

def annotate_events(events: pd.DataFrame, regime: pd.Series) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    out = events.copy()
    out.insert(0,"event_id",np.arange(len(out),dtype=int))
    out["htf_regime"] = [str(regime.loc[pd.Timestamp(t)]) for t in out.entry_time]
    out["htf_aligned"] = (
        ((out.side_sign == 1) & (out.htf_regime == "bull"))
        | ((out.side_sign == -1) & (out.htf_regime == "bear"))
    )
    return out

def build_matched_controls(data: pd.DataFrame, events: pd.DataFrame,
                           regime: pd.Series) -> pd.DataFrame:
    """One seeded same-day/same-side/same-regime non-sweep control per event."""
    rng = np.random.default_rng(SEED)
    controls = []
    for event in events.to_dict("records"):
        event_regime = event["htf_regime"]
        if event_regime == "unavailable":
            continue
        day = pd.Timestamp(event["day"],tz="UTC")
        start_i = data.index.searchsorted(day,side="left")
        end_i = data.index.searchsorted(day+pd.Timedelta(days=1),side="left")
        signal_i = data.index.get_indexer([pd.Timestamp(event["signal_time"])])[0]
        candidates = []
        for i in range(start_i,end_i):
            ts = data.index[i]
            minute = ts.hour*60+ts.minute
            if not (360 <= minute < 1080):
                continue
            if abs(i-signal_i) <= EXCLUSION_BARS:
                continue
            if str(regime.iloc[i]) != event_regime:
                continue
            last_i = i + max(HORIZONS.values()) - 1
            if last_i >= len(data) or data.segment.iloc[i:last_i+1].nunique() != 1:
                continue
            high_sweep,low_sweep = _is_sweep(
                data.iloc[i],float(event["range_high"]),float(event["range_low"])
            )
            if high_sweep or low_sweep:
                continue
            candidates.append(i)
        if not candidates:
            continue
        chosen = int(rng.choice(candidates))
        controls.append({
            "event_id":int(event["event_id"]),
            "control_time":data.index[chosen].isoformat(),
            "day":event["day"],"side":event["side"],
            "side_sign":int(event["side_sign"]),
            "htf_regime":event_regime,
            "htf_aligned":bool(event["htf_aligned"]),
            "entry":float(data.open.iloc[chosen]),
        })
    return pd.DataFrame(controls)

def paired_summary(event_returns: pd.DataFrame, control_returns: pd.DataFrame) -> dict:
    output = {}
    for horizon in ("1h","4h","8h"):
        e = event_returns[event_returns.horizon == horizon]
        c = control_returns[control_returns.horizon == horizon]
        if e.empty or c.empty:
            output[horizon] = {"status":"no eligible paired observations",
                "event_n":int(len(e)),"control_n":int(len(c))}
            continue
        p = e.merge(c[["event_id","gross_return_pct"]].rename(
            columns={"gross_return_pct":"control_gross_pct"}
        ),on="event_id",how="inner")
        if p.empty:
            output[horizon] = {"status":"no matched pairs","event_n":int(len(e))}
            continue
        result = {"paired_n":int(len(p)),
            "event_gross_pct":round(float(p.gross_return_pct.mean()),5),
            "control_gross_pct":round(float(p.control_gross_pct.mean()),5),
            "lift_gross_pct":round(float((p.gross_return_pct-p.control_gross_pct).mean()),5),
            "event_positive_gross_fraction":round(float((p.gross_return_pct>0).mean()),4),
            "event_long_n":int((p.side=="long").sum()),
            "event_short_n":int((p.side=="short").sum())}
        for bps in COSTS_BPS:
            key = int(bps)
            result[f"event_net_{key}bps_pct"] = round(float(p.gross_return_pct.mean()-bps/100.0),5)
            result[f"control_net_{key}bps_pct"] = round(float(p.control_gross_pct.mean()-bps/100.0),5)
            result[f"lift_{key}bps_pct"] = result["lift_gross_pct"]
        month = pd.to_datetime(p.entry_time,utc=True).dt.tz_convert(None).dt.to_period("M")
        monthly = p.assign(month=month).groupby("month").gross_return_pct.mean()
        result["positive_month_fraction_net_12bps"] = round(float((monthly>0.12).mean()),4)
        output[horizon] = result
    return output

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--days",type=int,default=730)
    parser.add_argument("--output-dir",default="research/results/session_sweep_4h_trend")
    args=parser.parse_args()
    if args.days < 700:
        raise SystemExit("Use at least 700 days to preserve the frozen chronological periods")
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    data=fetch_data(args.days)
    regime=completed_4h_regime(data)
    events=annotate_events(detect_events(data),regime)
    if events.empty:
        raise StudyError("No base session sweep events found")
    classified=events[events.htf_regime!="unavailable"].copy()
    if classified.empty:
        raise StudyError("No events have a fully warmed-up 4h trend regime")
    controls=build_matched_controls(data,classified,regime)
    if controls.empty:
        raise StudyError("No same-day/same-side/same-regime controls found")
    event_returns=evaluate(data,classified,"entry_time","event")
    control_returns=evaluate(data,controls,"control_time","control")
    if event_returns.empty or control_returns.empty:
        raise StudyError("No forward-return observations available")
    aligned_ids=set(classified.loc[classified.htf_aligned,"event_id"].astype(int))
    misaligned_ids=set(classified.loc[~classified.htf_aligned,"event_id"].astype(int))
    periods={
      "development_2024-11-14_to_2025-11-14":("2024-11-14","2025-11-14"),
      "validation_2025-11-14_to_2026-05-14":("2025-11-14","2026-05-14"),
      "final_holdout_2026-05-14_to_2026-11-14":("2026-05-14","2026-11-14"),
    }
    period_results={}
    for label,(start,end) in periods.items():
        lo=pd.Timestamp(start,tz="UTC"); hi=pd.Timestamp(end,tz="UTC")
        ids=set(classified.loc[
            (pd.to_datetime(classified.entry_time,utc=True)>=lo)
            & (pd.to_datetime(classified.entry_time,utc=True)<hi),"event_id"
        ].astype(int))
        for name,selected in (("all_classified",ids),("aligned",ids&aligned_ids),("misaligned",ids&misaligned_ids)):
            e=event_returns[event_returns.event_id.isin(selected)]
            c=control_returns[control_returns.event_id.isin(selected)]
            if name not in period_results:
                period_results[name]={}
            period_results[name][label]=paired_summary(e,c)
    all_ids=set(classified.event_id.astype(int))
    summaries={}
    for name,selected in (("all_classified",all_ids),("aligned",aligned_ids),("misaligned",misaligned_ids)):
        summaries[name]=paired_summary(
            event_returns[event_returns.event_id.isin(selected)],
            control_returns[control_returns.event_id.isin(selected)]
        )
    events.to_csv(out/"events_with_4h_regime.csv",index=False)
    controls.to_csv(out/"matched_controls.csv",index=False)
    event_returns.to_csv(out/"event_forward_returns.csv",index=False)
    control_returns.to_csv(out/"control_forward_returns.csv",index=False)
    data.to_csv(out/"btc_5m_source.csv.gz",compression="gzip")
    digest=hashlib.sha256(pd.util.hash_pandas_object(data,index=True).values.tobytes()).hexdigest()
    report={"status":"completed","symbol":"BTCUSD","timeframe":"5m","bars":int(len(data)),
        "first_bar_utc":data.index.min().isoformat(),"last_bar_utc":data.index.max().isoformat(),
        "gap_count":int((data.index.to_series().diff()>STEP*1.5).sum()),
        "duplicate_count":int(data.attrs.get("duplicate_count",0)),
        "data_hash_pandas_object_sha256":digest,
        "raw_event_count":int(len(events)),"classified_event_count":int(len(classified)),
        "aligned_event_count":int(len(aligned_ids)),"misaligned_event_count":int(len(misaligned_ids)),
        "regime_counts":classified.htf_regime.value_counts().to_dict(),
        "control_count":int(len(controls)),
        "rule":{"aligned_long":"low sweep fade only when completed 4h close > EMA50 > EMA200",
            "aligned_short":"high sweep fade only when completed 4h close < EMA50 < EMA200",
            "neutral_or_unavailable":"not trend-aligned","4h_bars":"48 contiguous closed 5m bars; right-labelled at close",
            "control":"same UTC day, same side and same 4h regime; random non-sweep bar; exclude +/-30m around signal",
            "seed":SEED,"round_trip_cost_bps":COSTS_BPS},
        "overall":summaries,"periods":{
            period:{
                "all_classified":period_results["all_classified"][period],
                "aligned":period_results["aligned"][period],
                "misaligned":period_results["misaligned"][period],
            } for period in periods
        },
        "limitations":["The 4h filter is preregistered for this experiment, but the unfiltered base event study was previously inspected.",
            "The final six-month block is held out from this filter's development and validation; it is not globally untouched from all prior exploratory work.",
            "Same-day matched controls are descriptive benchmarks, not randomized causal controls.",
            "This remains a forward-return event study, not a stop/target strategy backtest; no PF, R, or drawdown claim is appropriate.",
            "Costs are sensitivity assumptions; verified fee tier, spread, slippage and funding are not included."]}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
