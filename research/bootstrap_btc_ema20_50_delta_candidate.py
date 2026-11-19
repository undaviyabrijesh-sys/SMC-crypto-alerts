#!/usr/bin/env python3
"""Day/week/month cluster bootstrap audit for the frozen BTC EMA20/50 Delta candidate."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_SHA256 = "6464234b5f85c276fa2937ad6817b72070ad4f940f7ddf9e874edecf723d3686"
CONFIG = "ema20_50_atr1.5_tp3.0_none"
N_BOOT = 50_000

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def run(g, unit, seed):
    x=g.copy()
    if unit=="day": x["cluster"]=x.entry_time.dt.strftime("%Y-%m-%d")
    elif unit=="week": x["cluster"]=x.entry_time.dt.strftime("%G-W%V")
    elif unit=="month": x["cluster"]=x.entry_time.dt.strftime("%Y-%m")
    groups=[q.net_R_10bp.to_numpy(float) for _,q in x.groupby("cluster",sort=True)]
    if not groups: raise ValueError(f"No {unit} clusters")
    rng=np.random.default_rng(seed); means=np.empty(N_BOOT); totals=np.empty(N_BOOT)
    wins=np.empty(N_BOOT); pfs=np.empty(N_BOOT)
    for i in range(N_BOOT):
        picks=rng.integers(0,len(groups),size=len(groups))
        r=np.concatenate([groups[j] for j in picks])
        means[i]=r.mean(); totals[i]=r.sum(); wins[i]=(r>0).mean()
        w=r[r>0]; l=r[r<0]
        pfs[i]=w.sum()/abs(l.sum()) if len(l) and abs(l.sum()) else np.inf
    finite=pfs[np.isfinite(pfs)]
    return {
        "cluster_unit":unit,"clusters":len(groups),"bootstrap_resamples":N_BOOT,
        "mean_net_R_per_trade_ci95":np.quantile(means,[.025,.5,.975]).round(6).tolist(),
        "total_net_R_ci95":np.quantile(totals,[.025,.5,.975]).round(6).tolist(),
        "win_rate_ci95":np.quantile(wins,[.025,.5,.975]).round(6).tolist(),
        "profit_factor_ci95":np.quantile(finite,[.025,.5,.975]).round(6).tolist(),
        "probability_mean_net_R_positive":round(float((means>0).mean()),6),
        "probability_total_net_R_positive":round(float((totals>0).mean()),6),
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trades",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("ema20_50_cluster_bootstrap"))
    p.add_argument("--allow-different-hash",action="store_true")
    a=p.parse_args(); actual=sha(a.trades)
    if actual!=EXPECTED_SHA256 and not a.allow_different_hash:
        raise ValueError(f"Unexpected trade-ledger SHA256 {actual}; expected {EXPECTED_SHA256}")
    d=pd.read_csv(a.trades)
    x=d.loc[d.config_id.eq(CONFIG)].copy()
    x["entry_time"]=pd.to_datetime(x.entry_time,utc=True)
    if x.empty or x.net_R_10bp.isna().any(): raise ValueError("Candidate trades missing or non-finite")
    a.out.mkdir(parents=True,exist_ok=True)
    out={"source_sha256":actual,"source_rows":len(d),"candidate":CONFIG,"candidate_rows":len(x),"results":{}}
    rows=[]
    for sample,g in x.groupby("sample",sort=True):
        r=g.net_R_10bp.to_numpy(float); pos=np.maximum(r,0).sum()
        out["results"][sample]={
            "trades":len(g),"active_days":g.entry_time.dt.strftime("%Y-%m-%d").nunique(),
            "active_weeks":g.entry_time.dt.strftime("%G-W%V").nunique(),
            "active_months":g.entry_time.dt.strftime("%Y-%m").nunique(),
            "net_R_10bps":round(float(r.sum()),6),"mean_R_10bps":round(float(r.mean()),6),
            "win_rate_pct":round(float((r>0).mean()*100),4),
            "profit_factor":round(float(r[r>0].sum()/abs(r[r<0].sum())),6),
            "top3_winners_share_positive_R":round(float(np.sort(np.maximum(r,0))[-3:].sum()/pos),6) if pos else None,
            "cluster_bootstrap":{}
        }
        for unit,seed in [("day",20261119),("week",20261120),("month",20261121)]:
            z=run(g,unit,seed); out["results"][sample]["cluster_bootstrap"][unit]=z
            rows.append({"sample":sample,**z})
    (a.out/"bootstrap_results.json").write_text(json.dumps(out,indent=2)+"\n")
    pd.DataFrame(rows).to_csv(a.out/"bootstrap_summary.csv",index=False)
    print(json.dumps(out,indent=2))

if __name__=="__main__": main()
