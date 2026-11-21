#!/usr/bin/env python3
"""Cluster bootstrap audit for the frozen Binance BTCUSDT EMA20/50 replication."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_SHA256="b73ee6016deb161defe0bdbdeb183fdbc515fa3443185d6967c5bede45bd2910"
N=50_000

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()

def boot(g,unit,seed):
 x=g.copy()
 x["cluster"]=x.entry_time.dt.strftime("%Y-%m-%d" if unit=="day" else "%G-W%V" if unit=="week" else "%Y-%m")
 groups=[q.net_R_10bp.to_numpy(float) for _,q in x.groupby("cluster",sort=True)]
 rng=np.random.default_rng(seed); means=np.empty(N); totals=np.empty(N); pfs=np.empty(N)
 for i in range(N):
  r=np.concatenate([groups[j] for j in rng.integers(0,len(groups),size=len(groups))])
  means[i]=r.mean(); totals[i]=r.sum()
  w=r[r>0]; l=r[r<0]; pfs[i]=w.sum()/abs(l.sum()) if len(l) and abs(l.sum()) else np.inf
 finite=pfs[np.isfinite(pfs)]
 return {"clusters":len(groups),"mean_R_ci95":np.quantile(means,[.025,.5,.975]).round(6).tolist(),
  "total_R_ci95":np.quantile(totals,[.025,.5,.975]).round(6).tolist(),
  "PF_ci95":np.quantile(finite,[.025,.5,.975]).round(6).tolist(),
  "prob_mean_R_positive":round(float((means>0).mean()),6)}

def main():
 p=argparse.ArgumentParser(); p.add_argument("--trades",type=Path,required=True); p.add_argument("--out",type=Path,default=Path("binance_ema_bootstrap")); p.add_argument("--allow-different-hash",action="store_true"); a=p.parse_args()
 h=sha(a.trades)
 if h!=EXPECTED_SHA256 and not a.allow_different_hash: raise ValueError(f"Trade ledger SHA mismatch: {h}")
 d=pd.read_csv(a.trades); d.entry_time=pd.to_datetime(d.entry_time,utc=True)
 if d.net_R_10bp.isna().any(): raise ValueError("Non-finite net R")
 out={"source_sha256":h,"trades":len(d),"results":{}}
 for sample,g in d.groupby("sample",sort=True):
  r=g.net_R_10bp.to_numpy(float); pos=np.maximum(r,0).sum()
  out["results"][sample]={"trades":len(g),"net_R":round(float(r.sum()),6),"mean_R":round(float(r.mean()),6),
   "top3_winner_share_positive_R":round(float(np.sort(np.maximum(r,0))[-3:].sum()/pos),6) if pos else None,
   "bootstrap":{u:boot(g,u,20261122+i) for i,u in enumerate(["day","week","month"])}}
 a.out.mkdir(parents=True,exist_ok=True); (a.out/"bootstrap.json").write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps(out,indent=2))
if __name__=="__main__": main()
