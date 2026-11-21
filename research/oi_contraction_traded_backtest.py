#!/usr/bin/env python3
"""BTC OI-contraction + price-impulse backtest; experimental, no live use."""
from __future__ import annotations
import argparse, hashlib, itertools, json
from pathlib import Path
import numpy as np
import pandas as pd

H1, M15 = pd.Timedelta(hours=1), pd.Timedelta(minutes=15)
LOOKBACK, MIN_PERIODS, COOLDOWN_H, MAX_HOLD = 168, 72, 8, 32
COSTS = (6, 12, 20)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def load(path):
    d=pd.read_csv(path,parse_dates=["timestamp"])
    d["timestamp"]=pd.to_datetime(d.timestamp,utc=True)
    if d.timestamp.duplicated().any(): raise ValueError(f"{path}: duplicate timestamps")
    d=d.sort_values("timestamp").set_index("timestamp")
    for c in ("open","high","low","close"):
        d[c]=pd.to_numeric(d[c],errors="raise")
        if not np.isfinite(d[c].to_numpy(float)).all(): raise ValueError(f"{path}: invalid {c}")
    return d

def complete_hours(b):
    rows=[]
    for h,g in b.groupby(b.index.floor("1h"),sort=True):
        expected=pd.date_range(h,periods=4,freq="15min",tz="UTC")
        if len(g)==4 and g.index.equals(expected):
            rows.append((h+H1,float(g.close.iloc[-1])))
    if not rows: raise ValueError("no complete traded-price hours")
    x=pd.DataFrame(rows,columns=["available_time","close"]).set_index("available_time")
    x["price_1h"]=x.close.pct_change()
    return x

def build(oi,b,quality_filter=False):
    for idx,step,label in ((oi.index,H1,"OI 1h"),(b.index,M15,"BTC traded 15m")):
        if idx.to_series().diff().dropna().ne(step).any(): raise ValueError(f"{label} gap; no fill")
    h=complete_hours(b)
    o=oi.copy(); o.index=o.index+H1
    f=pd.DataFrame(index=o.index); f["oi_close"]=o.close.astype(float)
    # Non-positive OI sentinels are missing observations, never valid zero exposure.
    oi_levels=f.oi_close.where(f.oi_close>0)
    raw_oi_pct=oi_levels.pct_change(fill_method=None)
    f["oi_pct_raw"]=raw_oi_pct
    f["oi_spike_flag"]=raw_oi_pct.abs()>.20
    f["oi_pct"]=raw_oi_pct
    # In the quality sensitivity, remove >20% hourly jumps BEFORE rolling
    # z-score estimation. This also removes the following return if the
    # level snaps back, preventing a bad candle from contaminating the baseline.
    if quality_filter:
        f["oi_pct"]=f["oi_pct"].mask(f["oi_spike_flag"])
    r=f.oi_pct.rolling(LOOKBACK,min_periods=MIN_PERIODS)
    f["oi_z"]=(f.oi_pct-r.mean().shift(1))/r.std(ddof=0).shift(1).replace(0,np.nan)
    f=f.join(h[["price_1h","close"]],how="inner")
    q=f.price_1h.abs().rolling(LOOKBACK,min_periods=MIN_PERIODS)
    f["q90"],f["q95"]=q.quantile(.90).shift(1),q.quantile(.95).shift(1)
    f["trend24h"]=f.close.pct_change(24)
    f["regime"]=np.select([f.trend24h>.005,f.trend24h<-.005],["uptrend","downtrend"],default="range")
    prev=b.close.shift(1)
    tr=pd.concat([b.high-b.low,(b.high-prev).abs(),(b.low-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    v=f.dropna(subset=["oi_z","q90","q95","price_1h"])
    if v.empty: raise ValueError("no valid features")
    return v,atr

def bounds(idx):
    span=idx.max()-idx.min()
    return idx.min()+.70*span,idx.min()+.85*span

def split(t,a,b):
    return "train" if t<=a else ("validation" if t<=b else "oos")

def make_events(f,z,q,quality):
    x=f[(f.oi_pct<0)&(f.oi_z<=-z)&(f.price_1h.abs()>=f[f"q{q}"])].copy()
    if quality: x=x[(x.oi_pct.abs()<=.20)&(x.price_1h.abs()<=.05)]
    keep=[]; last=None
    for t in x.sort_index().index:
        if last is None or t-last>=pd.Timedelta(hours=COOLDOWN_H):
            keep.append(t); last=t
    return x.loc[keep]

def exit_fill(direction,o,h,l,stop,target):
    if direction==1:
        if l<=stop: return (min(o,stop) if o<stop else stop),"SL"
        if h>=target: return target,"TP"
    else:
        if h>=stop: return (max(o,stop) if o>stop else stop),"SL"
        if l<=target: return target,"TP"
    return None,None

def simulate(events,b,atr,f,sp,a,bb,mode,sm,trg,cost,z,q):
    end={"train":a,"validation":bb,"oos":f.index.max()}[sp]
    rows=[]; last_exit=-1
    for t,r in events.iterrows():
        if split(t,a,bb)!=sp or t not in b.index: continue
        i=b.index.get_loc(t)
        if i<=0 or i<=last_exit or pd.isna(atr.iloc[i-1]) or atr.iloc[i-1]<=0: continue
        if t+pd.Timedelta(hours=8)>end: continue
        impulse=1 if r.price_1h>0 else -1
        direction=impulse if mode=="continuation" else -impulse
        entry=float(b.open.iloc[i]); dist=sm*float(atr.iloc[i-1])
        if entry<=0 or dist<=0 or dist/entry>.05: continue
        stop=entry-direction*dist; target=entry+direction*trg*dist
        last=min(i+MAX_HOLD-1,len(b)-1)
        if last<i+MAX_HOLD-1: continue
        exit_price=reason=None; exit_i=None
        for j in range(i,last+1):
            o,h,l=map(float,(b.open.iloc[j],b.high.iloc[j],b.low.iloc[j]))
            fill,why=exit_fill(direction,o,h,l,stop,target)
            if why: exit_price,reason,exit_i=fill,why,j; break
        if exit_i is None: exit_i=last; exit_price=float(b.close.iloc[last]); reason="TIME"
        gross=direction*(exit_price-entry)/dist
        net=gross-(cost/10000)/(dist/entry)
        rows.append({"signal_time":t,"entry_time":b.index[i],"exit_time":b.index[exit_i],
            "split":sp,"mode":mode,"direction":"long" if direction==1 else "short",
            "zthr":z,"q":q,"stop_mult":sm,"target_r":trg,"cost_bps":cost,
            "entry":entry,"exit":exit_price,"reason":reason,"gross_r":gross,"net_r":net,
            "hold_bars":exit_i-i+1,"oi_pct":float(r.oi_pct),"oi_z":float(r.oi_z),
            "price_1h":float(r.price_1h),"regime":str(r.regime),"stop_frac":dist/entry})
        last_exit=exit_i
    return pd.DataFrame(rows)

def metrics(t):
    if t.empty:return {"trades":0}
    r=t.net_r.to_numpy(float); gp=r[r>0].sum(); gl=-r[r<0].sum()
    eq=np.r_[0.,np.cumsum(r)]; dd=eq-np.maximum.accumulate(eq)
    streak=mx=0
    for x in r: streak=streak+1 if x<0 else 0; mx=max(mx,streak)
    m=t.assign(month=t.exit_time.dt.strftime("%Y-%m")).groupby("month").net_r.sum()
    return {"trades":len(t),"win_rate_pct":float((r>0).mean()*100),
        "profit_factor":float(gp/gl) if gl else float("inf"),"net_r":float(r.sum()),
        "avg_r":float(r.mean()),"max_drawdown_r":float(dd.min()),
        "max_losing_streak":int(mx),"tp":int((t.reason=="TP").sum()),
        "sl":int((t.reason=="SL").sum()),"time":int((t.reason=="TIME").sum()),
        "positive_months_pct":float((m>0).mean()*100)}

def run(oi_path,price_path,out,quality=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    oi,b=load(oi_path),load(price_path);f,atr=build(oi,b,quality_filter=quality);a,bb=bounds(f.index)
    configs=list(itertools.product((1.5,2.5),(90,95),("continuation","reversal"),(1.,1.5),(1.5,2.,3.)))
    matrix=[];trades=[];costs=[];monthly=[];regimes=[]
    for z,q,mode,sm,trg in configs:
        ev=make_events(f,z,q,quality)
        tr=simulate(ev,b,atr,f,"train",a,bb,mode,sm,trg,12,z,q)
        va=simulate(ev,b,atr,f,"validation",a,bb,mode,sm,trg,12,z,q)
        x={"zthr":z,"q":q,"mode":mode,"stop_mult":sm,"target_r":trg}
        st,sv=metrics(tr),metrics(va)
        x.update({f"train_{k}":v for k,v in st.items()})
        x.update({f"validation_{k}":v for k,v in sv.items()})
        tg=st.get("trades",0)>=40 and st.get("profit_factor",0)>1 and st.get("net_r",0)>0
        vg=sv.get("trades",0)>=20 and sv.get("profit_factor",0)>1 and sv.get("net_r",0)>0
        x["train_gate"]=bool(tg);x["validation_gate"]=bool(tg and vg);matrix.append(x)
        if tg:
            selected_splits=("train","validation","oos") if vg else ("train","validation")
            for sp in selected_splits:
                for c in COSTS:
                    t=simulate(ev,b,atr,f,sp,a,bb,mode,sm,trg,c,z,q);m=metrics(t)
                    costs.append({"zthr":z,"q":q,"mode":mode,"stop_mult":sm,"target_r":trg,
                                  "split":sp,"cost_bps":c,**m})
                    if c==12 and not t.empty:
                        trades.append(t)
                        mm=t.assign(month=t.exit_time.dt.strftime("%Y-%m")).groupby("month").net_r.sum()
                        for month,val in mm.items():
                            monthly.append({"zthr":z,"q":q,"mode":mode,"stop_mult":sm,
                                "target_r":trg,"split":sp,"month":month,"net_r":val})
                        rg=t.groupby("regime").net_r.agg(["count","sum","mean"]).reset_index()
                        for r in rg.to_dict("records"):
                            regimes.append({"zthr":z,"q":q,"mode":mode,"stop_mult":sm,
                                "target_r":trg,"split":sp,**r})
    md=pd.DataFrame(matrix);md.to_csv(out/"matrix.csv",index=False)
    pd.DataFrame(costs).to_csv(out/"cost_sensitivity.csv",index=False)
    if trades:pd.concat(trades,ignore_index=True).to_csv(out/"selected_trades_12bp.csv",index=False)
    pd.DataFrame(monthly).to_csv(out/"monthly.csv",index=False)
    pd.DataFrame(regimes).to_csv(out/"regimes.csv",index=False)
    events_count={f"z{z}_q{q}":len(make_events(f,z,q,quality)) for z,q in ((1.5,90),(1.5,95),(2.5,90),(2.5,95))}
    meta={"classification":"experimental trade backtest; no live use",
      "oi_rows":len(oi),"oi_first_open_utc":oi.index.min().isoformat(),"oi_last_open_utc":oi.index.max().isoformat(),
      "oi_sha256":sha(oi_path),"price_15m_rows":len(b),"price_first_open_utc":b.index.min().isoformat(),
      "price_last_open_utc":b.index.max().isoformat(),"price_15m_sha256":sha(price_path),
      "valid_feature_rows":len(f),"valid_feature_first_available_utc":f.index.min().isoformat(),
      "valid_feature_last_available_utc":f.index.max().isoformat(),
      "train_end_utc":a.isoformat(),"validation_end_utc":bb.isoformat(),
      "split":"chronological 70/15/15","configurations":len(configs),
      "training_eligible":int(md.train_gate.sum()),"validation_passes":int(md.validation_gate.sum()),
      "event_counts_after_8h_cooldown":events_count,"quality_filter_enabled":quality,
      "quality_filter_definition":"mask non-positive OI levels as missing and mask >20% OI close-to-close jumps BEFORE rolling z-score estimation; also exclude candidate events with abs 1h traded-price return >5%; post-inspection sensitivity only",
      "oi_nonpositive_levels":int((oi.close<=0).sum()),
      "oi_gt20pct_changes":int((oi.close.where(oi.close>0).pct_change(fill_method=None).abs()>.20).sum()),
      "signal":"1h OI pct change <0 and z-score <= -1.5/-2.5 against prior 168h; abs traded-price 1h close return >= prior 168h q90/q95",
      "execution":"next 15m open after OI close; ATR14 Wilder from prior completed 15m bar; 1.0/1.5 ATR stop; 1.5/2/3R target; 8h max hold; 8h event cooldown; one position/config",
      "costs":"12bp primary; 6/12/20bp sensitivity for train-eligible candidates; OOS only after validation pass; funding excluded",
      "fills":"same-bar SL first; adverse stop gap at worse open; target gap at target; time exit at final 15m close",
      "selection_gates":"train >=40 trades, validation >=20 trades; PF>1 and net R>0 in both; OOS only after both gates",
      "notes":["OI units/sampling semantics are unverified; raw data contain extreme hourly changes.",
        "Non-positive OI levels are treated as missing in both modes; quality sensitivity masks >20% OI changes before z-score calculation so outliers cannot contaminate the rolling baseline.",
        "Primary mode retains positive >20% OI changes; quality-filter mode is a post-inspection sensitivity.",
        "No separate spread model; flat round-trip cost sensitivity only."]}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps(meta,indent=2));print(md[md.train_gate].to_string(index=False))

def self_test():
    assert exit_fill(1,100,120,80,90,110)==(90,"SL")
    assert exit_fill(-1,100,120,80,110,90)==(110,"SL")
    assert exit_fill(1,85,95,80,90,110)==(85,"SL")
    assert exit_fill(1,115,120,112,90,110)==(110,"TP")
    assert exit_fill(-1,115,120,112,110,90)==(115,"SL")
    assert exit_fill(-1,85,88,80,110,90)==(90,"TP")
    # A large OI level jump and snap-back must be absent from the quality
    # z-score input, rather than being filtered only after the z-score exists.
    oi_idx=pd.date_range("2024-01-01",periods=220,freq="1h")
    levels=1000.0+np.arange(220,dtype=float)
    levels[180]*=1.5
    levels[190]=0.0
    oi_test=pd.DataFrame({"open":levels,"high":levels,"low":levels,"close":levels},index=oi_idx)
    px_idx=pd.date_range(oi_idx[0],periods=220*4,freq="15min")
    px_close=50000.0+np.arange(len(px_idx),dtype=float)
    px_test=pd.DataFrame({"open":px_close,"high":px_close+5,"low":px_close-5,
        "close":px_close,"volume":1.0},index=px_idx)
    raw_features,_=build(oi_test,px_test,quality_filter=False)
    clean_features,_=build(oi_test,px_test,quality_filter=True)
    spike_time=oi_idx[180]+H1
    assert spike_time in raw_features.index
    assert spike_time not in clean_features.index
    assert spike_time+H1 not in clean_features.index
    zero_time=oi_idx[190]+H1
    assert zero_time not in raw_features.index and zero_time+H1 not in raw_features.index
    print("7 execution/data-quality self-tests passed")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--oi-csv",type=Path);p.add_argument("--price-15m-csv",type=Path)
    p.add_argument("--output-dir",type=Path);p.add_argument("--quality-filter",action="store_true")
    p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:self_test();return
    if not a.oi_csv or not a.price_15m_csv or not a.output_dir:p.error("provide --oi-csv, --price-15m-csv and --output-dir")
    run(a.oi_csv,a.price_15m_csv,a.output_dir,a.quality_filter)

if __name__=="__main__":main()
