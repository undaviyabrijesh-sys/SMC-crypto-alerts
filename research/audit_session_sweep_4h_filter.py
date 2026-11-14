#!/usr/bin/env python3
"""Independent robustness audit for BTC session sweep + 4h trend event study.

Adds a stricter 3-hour UTC time-bucket matched control, splits neutral from
countertrend events, and estimates 7-observation moving-block bootstrap CIs.
Reads only the reproducible outputs of btc_session_sweep_4h_trend_filter.py.
This remains a forward-return event study, not a stop/target backtest.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

from btc_session_range_sweep_event_study import _is_sweep, HORIZONS, COSTS_BPS, STEP

SEED = 20261115
EXCLUSION_BARS = 6
BLOCK_LENGTH = 7
BOOTSTRAP_REPS = 3000
PERIODS = {
    "development": ("2024-11-14", "2025-11-14"),
    "validation": ("2025-11-14", "2026-05-14"),
    "final_holdout": ("2026-05-14", "2026-11-14"),
}

def completed_regime(data: pd.DataFrame) -> pd.Series:
    x=data.copy()
    h=x[["open","high","low","close"]].resample("4h",label="right",closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last"})
    count=x.close.resample("4h",label="right",closed="left").count()
    segs=x.segment.resample("4h",label="right",closed="left").nunique()
    h=h.loc[count.eq(48)&segs.eq(1)].dropna().copy()
    h["segment"]=h.index.to_series().diff().ne(pd.Timedelta(hours=4)).cumsum().to_numpy()
    h["ema50"]=h.groupby("segment").close.transform(
        lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean())
    h["ema200"]=h.groupby("segment").close.transform(
        lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
    bull=(h.close>h.ema50)&(h.ema50>h.ema200)
    bear=(h.close<h.ema50)&(h.ema50<h.ema200)
    h["regime"]=np.select([bull,bear],["bull","bear"],default="neutral")
    return h.regime.reindex(data.index,method="ffill").fillna("unavailable")

def category(side: str, regime: str) -> str:
    if regime in ("neutral","unavailable"):
        return "neutral"
    if (side=="long" and regime=="bull") or (side=="short" and regime=="bear"):
        return "aligned"
    return "countertrend"

def make_time_bucket_controls(data: pd.DataFrame, events: pd.DataFrame,
                              regime: pd.Series) -> pd.DataFrame:
    rng=np.random.default_rng(SEED)
    rows=[]
    for event in events.to_dict("records"):
        day=pd.Timestamp(event["day"],tz="UTC")
        start=data.index.searchsorted(day,side="left")
        end=data.index.searchsorted(day+pd.Timedelta(days=1),side="left")
        signal_i=data.index.get_indexer([pd.Timestamp(event["signal_time"])])[0]
        bucket=pd.Timestamp(event["signal_time"]).hour//3
        candidates=[]
        for i in range(start,end):
            ts=data.index[i]
            if ts.hour//3!=bucket or not (6<=ts.hour<18):
                continue
            if abs(i-signal_i)<=EXCLUSION_BARS:
                continue
            last=i+max(HORIZONS.values())-1
            if last>=len(data) or data.segment.iloc[i:last+1].nunique()!=1:
                continue
            if str(regime.iloc[i])!=str(event["htf_regime"]):
                continue
            high_sweep,low_sweep=_is_sweep(
                data.iloc[i],float(event["range_high"]),float(event["range_low"]))
            if high_sweep or low_sweep:
                continue
            candidates.append(i)
        if not candidates:
            continue
        i=int(rng.choice(candidates))
        rows.append({"event_id":int(event["event_id"]),
            "control_time":data.index[i].isoformat(),"day":event["day"],
            "side":event["side"],"side_sign":int(event["side_sign"]),
            "htf_regime":event["htf_regime"],
            "category":category(event["side"],event["htf_regime"]),
            "entry":float(data.open.iloc[i]),
            "control_utc_3h_bucket":int(bucket)})
    return pd.DataFrame(rows)

def evaluate_controls(data: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for item in controls.to_dict("records"):
        i=data.index.get_indexer([pd.Timestamp(item["control_time"])])[0]
        if i<0: continue
        for horizon,bars in HORIZONS.items():
            j=i+bars-1
            if j>=len(data) or data.segment.iloc[i:j+1].nunique()!=1:
                continue
            gross=(float(data.close.iloc[j])/float(item["entry"])-1.0)*int(item["side_sign"])*100.0
            rows.append({**item,"horizon":horizon,"exit_time":data.index[j].isoformat(),
                "gross_return_pct":gross})
    return pd.DataFrame(rows)

def block_ci(values: np.ndarray, seed: int) -> list[float] | None:
    x=np.asarray(values,dtype=float)
    x=x[np.isfinite(x)]
    n=len(x)
    if n<10: return None
    rng=np.random.default_rng(seed)
    blocks=int(np.ceil(n/BLOCK_LENGTH))
    starts=rng.integers(0,n,size=(BOOTSTRAP_REPS,blocks))
    idx=(starts[:,:,None]+np.arange(BLOCK_LENGTH)[None,None,:])%n
    idx=idx.reshape(BOOTSTRAP_REPS,-1)[:,:n]
    means=x[idx].mean(axis=1)
    return [round(float(v),6) for v in np.quantile(means,[0.025,0.975])]

def paired_stats(events: pd.DataFrame, controls: pd.DataFrame, label: str) -> dict:
    output={}
    for horizon in ("1h","4h","8h"):
        e=events[events.horizon==horizon]
        c=controls[controls.horizon==horizon]
        p=e.merge(c[["event_id","gross_return_pct"]].rename(
            columns={"gross_return_pct":"control_gross_pct"}),on="event_id",how="inner")
        if p.empty:
            output[horizon]={"paired_n":0}
            continue
        p=p.sort_values("entry_time")
        gross=p.gross_return_pct.to_numpy(float)
        control=p.control_gross_pct.to_numpy(float)
        lift=gross-control
        result={"paired_n":int(len(p)),
            "event_mean_gross_pct":round(float(gross.mean()),5),
            "event_mean_net_6bps_pct":round(float((gross-0.06).mean()),5),
            "event_mean_net_12bps_pct":round(float((gross-0.12).mean()),5),
            "event_mean_net_20bps_pct":round(float((gross-0.20).mean()),5),
            "control_mean_net_12bps_pct":round(float((control-0.12).mean()),5),
            "paired_lift_pct":round(float(lift.mean()),5),
            "event_win_rate_net_12bps":round(float(((gross-0.12)>0).mean()),4),
            "positive_event_month_fraction_net_12bps":round(float(
                (p.assign(month=pd.to_datetime(p.entry_time,utc=True).dt.to_period("M"),
                          net=gross-0.12).groupby("month").net.mean()>0).mean()),4),
            "paired_lift_95pct_block_bootstrap_ci":block_ci(lift,SEED+len(p)+len(label)),
            "event_net_12bps_95pct_block_bootstrap_ci":block_ci(gross-0.12,SEED+2*len(p)+len(label))}
        output[horizon]=result
    return output

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-dir",default="research/results/session_sweep_4h_trend")
    args=ap.parse_args()
    root=Path(args.input_dir)
    data=pd.read_csv(root/"btc_5m_source.csv.gz",index_col=0,parse_dates=True)
    data.index=pd.to_datetime(data.index,utc=True)
    data["segment"]=pd.to_numeric(data.segment,errors="raise").astype(int)
    events=pd.read_csv(root/"events_with_4h_regime.csv")
    events["category"]=[category(r.side,r.htf_regime) for r in events.itertuples()]
    events["entry_time"]=pd.to_datetime(events.entry_time,utc=True)
    original_regime=completed_regime(data)
    check=events.entry_time.map(original_regime)
    mismatches=int((check.to_numpy()!=events.htf_regime.to_numpy()).sum())
    if mismatches:
        raise RuntimeError(f"4h regime reconstruction mismatch count={mismatches}")
    controls=make_time_bucket_controls(data,events,original_regime)
    control_returns=evaluate_controls(data,controls)
    event_returns=pd.read_csv(root/"event_forward_returns.csv")
    event_returns["entry_time"]=pd.to_datetime(event_returns.entry_time,utc=True)
    event_returns=event_returns.merge(events[["event_id","category"]],on="event_id",how="left")
    control_returns=control_returns.merge(events[["event_id","category"]],on="event_id",how="left")
    controls.to_csv(root/"time_bucket_matched_controls.csv",index=False)
    control_returns.to_csv(root/"time_bucket_control_returns.csv",index=False)
    summaries={}
    for period,(start,end) in PERIODS.items():
        lo=pd.Timestamp(start,tz="UTC"); hi=pd.Timestamp(end,tz="UTC")
        summaries[period]={}
        for group in ("aligned","countertrend","neutral"):
            selected=events.loc[(events.category==group)&(events.entry_time>=lo)&(events.entry_time<hi),"event_id"]
            ids=set(selected.astype(int))
            e=event_returns[event_returns.event_id.isin(ids)].copy()
            c=control_returns[control_returns.event_id.isin(ids)].copy()
            # A period's forward outcome must be fully observed before its end.
            e=e[pd.to_datetime(e.exit_time,utc=True)<=hi]
            c=c[pd.to_datetime(c.exit_time,utc=True)<=hi]
            summaries[period][group]=paired_stats(e,c,period+group)
    overall={}
    for group in ("aligned","countertrend","neutral"):
        ids=set(events.loc[events.category==group,"event_id"].astype(int))
        overall[group]=paired_stats(event_returns[event_returns.event_id.isin(ids)],
            control_returns[control_returns.event_id.isin(ids)],"overall"+group)
    report={"status":"completed","data_rows":int(len(data)),
        "first_bar_utc":data.index.min().isoformat(),"last_bar_utc":data.index.max().isoformat(),
        "source_data_hash_from_primary_report":json.loads((root/"report.json").read_text()).get("data_hash_pandas_object_sha256"),
        "regime_reconstruction_mismatches":mismatches,
        "events":int(len(events)),"categories":events.category.value_counts().to_dict(),
        "time_bucket_control_matches":int(len(controls)),
        "time_bucket_control_match_rate":round(float(len(controls)/len(events)),4) if len(events) else 0,
        "control_definition":"same UTC day, same side, same completed 4h regime, same 3h UTC time bucket, non-sweep bar, outside +/-30m of event",
        "bootstrap":{"method":"circular moving-block bootstrap on event-ordered paired observations",
            "block_length_observations":BLOCK_LENGTH,"replicates":BOOTSTRAP_REPS,"seed_base":SEED},
        "overall":overall,"periods":summaries,
        "limitations":["Still a forward-return study; no stop/target PF, R, or trade drawdown is claimed.",
            "The 3h bucket match improves time-of-day comparability but does not create randomized causal controls.",
            "Moving-block bootstrap is an uncertainty diagnostic, not a proof of independence or causality.",
            "6/12/20bp round-trip costs remain assumptions; spread, market impact, funding and exact fee tier are not included."]}
    (root/"robustness_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
