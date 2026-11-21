#!/usr/bin/env python3
"""Recalculate PDRT trades using public Delta maker/taker rates on entry and exit notionals."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

MODELS={"maker_maker_4bps":(.0002,.0002),"maker_taker_7bps":(.0002,.0005),
        "taker_taker_10bps":(.0005,.0005),"stress_20bps":(.001,.001)}
TARGETS=("1p5","2p0","3p0")
SAMPLES=("development","validation")

def summarize(g,entry_rate,exit_rate):
    fee=g.entry.astype(float)*entry_rate+g.exit_price.astype(float)*exit_rate
    cost_r=fee/g.risk.astype(float); net=g.gross_r.astype(float)-cost_r
    v=net.to_numpy(float); w=v[v>0]; l=v[v<0]
    pf=float(w.sum()/abs(l.sum())) if len(l) else None
    eq=np.cumsum(v); dd=eq-np.maximum.accumulate(np.r_[0.,eq])[1:]
    streak=mx=0
    for x in v: streak=streak+1 if x<0 else 0; mx=max(mx,streak)
    months=pd.to_datetime(g.entry_time,utc=True).dt.strftime("%Y-%m").to_numpy()
    mon=pd.Series(v).groupby(months).sum()
    return {"trades":len(v),"win_rate_pct":100*float((v>0).mean()),"profit_factor":pf,
      "net_R":float(v.sum()),"avg_net_R":float(v.mean()),"max_drawdown_R":float(dd.min()),
      "max_losing_streak":mx,"positive_months":int((mon>0).sum()),"active_months":len(mon),
      "mean_cost_R":float(cost_r.mean()),"median_cost_R":float(cost_r.median())}

def self_test():
    g=pd.DataFrame({"entry":[100000.],"exit_price":[101000.],"risk":[500.],
      "gross_r":[2.],"entry_time":["2026-01-01T00:00:00Z"]})
    m=summarize(g,.0005,.0005)
    assert abs(m["net_R"]-(2.-.201))<1e-12
    print("PASS entry/exit notional fee arithmetic")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--trades-dir",type=Path,default=Path("historical_data/pdrt"))
    ap.add_argument("--output",type=Path,default=Path("research/results/pdrt_public_fee_recalc.csv"))
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: self_test(); return
    rows=[]
    for target in TARGETS:
      for sample in SAMPLES:
        g=pd.read_csv(a.trades_dir/f"pdrt_trades_{target}_{sample}.csv")
        if (g.risk<=0).any(): raise ValueError("Non-positive trade risk")
        for label,(er,xr) in MODELS.items():
          rows.append({"target_R":float(target.replace("p",".")),"sample":sample,
            "fee_model":label,"entry_fee_rate":er,"exit_fee_rate":xr,**summarize(g,er,xr)})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    out=pd.DataFrame(rows); out.to_csv(a.output,index=False); print(out.to_string(index=False))
if __name__=="__main__": main()
