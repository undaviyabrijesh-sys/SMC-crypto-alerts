#!/usr/bin/env python3
"""Delta BTC/ETH funding-sentiment event study (exploratory; OOS intentionally untouched)."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
FUNDING_BAR = pd.Timedelta(hours=1)
START = pd.Timestamp("2025-09-09T00:00:00Z")
SLOTS = (0, 8, 16)
HORIZONS = {"1h": 4, "4h": 16}
COSTS = (4, 7, 10, 20)
BOOT_REPS, SEED = 5000, 20261116

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20), b""): h.update(b)
    return h.hexdigest()

def load(path, step, funding=False):
    d=pd.read_csv(path)
    d["timestamp"]=pd.to_datetime(d.timestamp,utc=True,errors="coerce")
    bad_ts=int(d.timestamp.isna().sum()); d=d.dropna(subset=["timestamp"])
    dup=int(d.timestamp.duplicated().sum())
    d=d.drop_duplicates("timestamp",keep="last").sort_values("timestamp").set_index("timestamp")
    for c in ("open","high","low","close","volume"):
        d[c]=pd.to_numeric(d[c],errors="coerce")
    finite=np.isfinite(d[["open","high","low","close","volume"]].to_numpy(float)).all(axis=1)
    positive=np.ones(len(d),dtype=bool) if funding else (d[["open","high","low","close"]]>0).all(axis=1).to_numpy()
    shape=((d.high>=d[["open","close","low"]].max(axis=1)) &
           (d.low<=d[["open","close","high"]].min(axis=1))).to_numpy()
    d=d.loc[finite & positive & shape,["open","high","low","close","volume"]]
    delta=d.index.to_series().diff().dropna()
    return d,{"rows":len(d),"invalid_timestamps":bad_ts,"duplicates_removed":dup,
              "gaps":int((delta!=step).sum()),"start":d.index.min().isoformat(),
              "end_open":d.index.max().isoformat(),"sha256":digest(path)}

def regime_4h(p):
    x=p.copy()
    x["seg"]=x.index.to_series().diff().ne(BAR).cumsum()
    kw={"label":"right","closed":"left"}
    h=x.resample("4h",**kw).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
    cnt=x.close.resample("4h",**kw).count()
    seg=x.seg.resample("4h",**kw).nunique()
    h=h.loc[(cnt==16)&(seg==1)].dropna()
    h["seg"]=h.index.to_series().diff().ne(pd.Timedelta(hours=4)).cumsum()
    h["e50"]=h.groupby("seg").close.transform(lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean())
    h["e200"]=h.groupby("seg").close.transform(lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
    h["regime"]=np.select([(h.close>h.e50)&(h.e50>h.e200),(h.close<h.e50)&(h.e50<h.e200)],
                          ["bull","bear"],default="neutral")
    h.loc[h.e200.isna(),"regime"]="unavailable"
    return h

def build_blocks(asset,p,f):
    h=regime_4h(p)
    f=f.loc[(f.index>=START)&(f.index.minute==0)&(f.index.hour.isin(SLOTS))]
    out=[]
    for t,r in f.iterrows():
        entry_t=t+FUNDING_BAR
        if entry_t not in p.index: continue
        i=int(p.index.get_loc(entry_t))
        j=h.index.searchsorted(entry_t,side="right")-1
        reg=str(h.regime.iloc[j]) if j>=0 else "unavailable"
        if reg=="unavailable": continue
        z={"asset":asset,"block_time":t,"entry_time":entry_t,"slot":t.hour,
           "weekday":t.dayofweek,"rate":float(r.close),"regime":reg}
        ok=True
        for name,n in HORIZONS.items():
            k=i+n-1
            if k>=len(p) or p.index[k]-p.index[i]!=BAR*(n-1): ok=False; break
            xt=p.index[k]+BAR
            if xt!=entry_t+pd.Timedelta(hours=int(name[:-1])) or xt>=t+pd.Timedelta(hours=8):
                ok=False; break
            z[name]=float((p.close.iloc[k]/p.open.iloc[i]-1)*10000)
            z[name+"_exit"]=xt
        if ok: out.append(z)
    return pd.DataFrame(out)

def sample_of(t,dev_end,val_end):
    return "development" if t<dev_end else ("validation" if t<val_end else "untouched_oos")

def match(ev,co,sample):
    if ev.empty or co.empty: return pd.DataFrame()
    et=pd.DatetimeIndex(ev.block_time).sort_values()
    keep=[]
    for t in co.block_time:
        k=et.searchsorted(t)
        near=(k<len(et) and abs((et[k]-t).total_seconds())<8*3600) or (k>0 and abs((et[k-1]-t).total_seconds())<8*3600)
        keep.append(not near)
    co=co.loc[np.asarray(keep)].copy(); used=set(); rows=[]
    for _,e in ev.sort_values("block_time").iterrows():
        c=co[(co.weekday==e.weekday)&(co.slot==e.slot)&(co.regime==e.regime)&
             ((co.block_time-e.block_time).abs()<=pd.Timedelta(days=35))&(~co.block_time.isin(used))]
        if c.empty: continue
        dist=(c.block_time-e.block_time).abs(); m=dist.min()
        q=c.loc[dist.eq(m)].sort_values("block_time").iloc[0]; used.add(q.block_time)
        rows.append({"asset":e.asset,"sample":sample,"event_time":e.block_time,
          "control_time":q.block_time,"date_utc":e.block_time.date().isoformat(),
          "1h_lift":e["1h"]-q["1h"],"4h_lift":e["4h"]-q["4h"],
          "1h_event":e["1h"],"1h_control":q["1h"],"4h_event":e["4h"],"4h_control":q["4h"]})
    return pd.DataFrame(rows)

def metrics(g,h,cost):
    if g.empty: return {"trades":0}
    v=g[h].to_numpy(float)-cost; w=v[v>0]; l=v[v<0]
    pf=float(w.sum()/abs(l.sum())) if len(l) else None
    eq=np.cumsum(v); dd=eq-np.maximum.accumulate(np.r_[0.,eq])[1:]
    streak=mx=0
    for x in v: streak=streak+1 if x<0 else 0; mx=max(mx,streak)
    months=pd.to_datetime(g.block_time,utc=True).dt.strftime("%Y-%m").to_numpy()
    mon=pd.Series(v).groupby(months).sum()
    return {"trades":len(v),"win_rate_pct":100*float((v>0).mean()),"profit_factor":pf,
      "mean_net_bps":float(v.mean()),"event_sequence_max_drawdown_bps":float(dd.min()),
      "max_losing_streak":mx,"positive_months":int((mon>0).sum()),"active_months":len(mon)}

def ci_day_cluster(p,h,reps=BOOT_REPS):
    if p.empty: return None
    v=p[h+"_lift"].to_numpy(float); d=p.date_utc.to_numpy(); u=np.unique(d)
    if len(u)<10: return None
    groups={x:v[d==x] for x in u}; rng=np.random.default_rng(SEED); b=np.empty(reps)
    for i in range(reps):
        take=rng.choice(u,len(u),replace=True); b[i]=np.concatenate([groups[x] for x in take]).mean()
    return np.quantile(b,[.025,.975]).tolist()

def run(price_dir,funding_dir,out):
    out.mkdir(parents=True,exist_ok=True); blocks={}; dq={}
    for a in ("BTC","ETH"):
        p,dq[a+"_price"]=load(price_dir/f"{a}_15m.csv",BAR)
        f,dq[a+"_funding"]=load(funding_dir/f"{a}_funding_1h.csv",FUNDING_BAR,True)
        blocks[a]=build_blocks(a,p,f)
    common=sorted(set(blocks["BTC"].block_time)&set(blocks["ETH"].block_time))
    dev_end=common[int(.70*len(common))]; val_end=common[int(.85*len(common))]
    for a in blocks: blocks[a]["sample"]=blocks[a].block_time.map(lambda t:sample_of(t,dev_end,val_end))
    defs={
      "negative_funding_long":(lambda x:x.rate<0,lambda x:x.rate>=0),
      "below_neutral_0p01_long":(lambda x:x.rate<.01,lambda x:x.rate>=.01)}
    summaries=[]; pairs=[]; evrows=[]
    for name,(emask,cmask) in defs.items():
      for a,b in blocks.items():
        for sample in ("development","validation"):
          end=dev_end if sample=="development" else val_end
          z=b.loc[b["sample"]==sample].copy(); z=z.loc[z["4h_exit"]<=end]
          ev=z.loc[emask(z)].copy(); co=z.loc[cmask(z)].copy()
          if not ev.empty:
            ev.insert(0,"definition",name); ev["sample"]=sample; evrows.append(ev)
          q=match(ev,co,sample)
          if not q.empty: q.insert(0,"definition",name); pairs.append(q)
          for h in HORIZONS:
            for cost in COSTS:
              summaries.append({"definition":name,"asset":a,"sample":sample,"horizon":h,
                "cost_bps":cost,"events":len(ev),"matched_pairs":len(q),**metrics(ev,h,cost)})
    s=pd.DataFrame(summaries); q=pd.concat(pairs,ignore_index=True) if pairs else pd.DataFrame()
    e=pd.concat(evrows,ignore_index=True) if evrows else pd.DataFrame(); lift=[]
    if not q.empty:
      for (name,a,sample),g in q.groupby(["definition","asset","sample"]):
        for h in HORIZONS:
          ci=ci_day_cluster(g,h)
          lift.append({"definition":name,"asset":a,"sample":sample,"horizon":h,
            "matched_pairs":len(g),"mean_lift_gross_bps":g[h+"_lift"].mean(),
            "ci95_low":ci[0] if ci else None,"ci95_high":ci[1] if ci else None})
    l=pd.DataFrame(lift)
    s.to_csv(out/"summary.csv",index=False); q.to_csv(out/"matched_pairs.csv",index=False)
    e.to_csv(out/"events_dev_validation.csv",index=False); l.to_csv(out/"paired_lift.csv",index=False)
    meta={"status":"completed_exploratory_event_study","common_blocks":len(common),
      "development_end_utc":dev_end.isoformat(),"validation_end_utc":val_end.isoformat(),
      "oos":"not evaluated","data":dq,
      "rules":"Raw 1h funding candle at 00/08/16 UTC is observed after one hour; next 15m open entry; 1h/4h forward returns; 4h exit before next settlement; no funding cashflow.",
      "matching":"Same asset, weekday, slot and completed 4h EMA50/EMA200 regime; nearest non-event within 35 days, no replacement; exclude controls within 8h of events.",
      "costs_bps_round_trip":list(COSTS),
      "limitations":["Exploratory forward-return study, not stop-defined strategy; R/account DD not applicable.",
        "Funding rate is a lagged sentiment feature only; no funding cashflow applied.",
        "Historical rate-to-settlement timestamp mapping remains unresolved.",
        "Flat costs omit spread/market impact; actual user fee tier unavailable.",
        "Matched controls are observational; OOS not evaluated."]}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    return meta

def self_test():
    t=pd.Timestamp("2026-01-01T00:00Z")
    assert t+FUNDING_BAR==pd.Timestamp("2026-01-01T01:00Z")
    assert t+FUNDING_BAR+pd.Timedelta(hours=4)<t+pd.Timedelta(hours=8)
    assert abs((.0005+.0005)*10000-10)<1e-12
    assert abs((.0002+.0005)*10000-7)<1e-12
    assert abs((.0002+.0002)*10000-4)<1e-12
    print("PASS lag, settlement window and maker/taker fee arithmetic")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--price-dir",type=Path,default=Path("historical_data/funding_sentiment"))
    ap.add_argument("--funding-dir",type=Path,default=Path("historical_data/derivatives"))
    ap.add_argument("--output-dir",type=Path,default=Path("research/results/funding_sentiment"))
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: self_test()
    else: print(json.dumps(run(a.price_dir,a.funding_dir,a.output_dir),indent=2))
