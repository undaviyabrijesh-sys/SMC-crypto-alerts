#!/usr/bin/env python3
"""Independent audit of the CRT study's summary and trade ledger."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
ap=argparse.ArgumentParser()
ap.add_argument("--results-dir",type=Path,default=Path(__file__).resolve().parent.parent/"results")
root=ap.parse_args().results_dir
meta=json.loads((root/"metadata.json").read_text())
summary=pd.read_csv(root/"summary_dev_val_costs.csv")
trades=pd.read_csv(root/"trades_dev_val.csv")
assert len(summary)==80 and set(summary.cost_bps)=={0,4,7,10,20}
assert set(trades.split)=={"development","validation"}
def independent(g,cost):
    if g.empty:return (0,np.nan,np.nan,0.,np.nan,0.,0,np.nan)
    net=g.gross_R.values-(cost/10000*g.entry.values)/g.risk_points.values
    pos=net[net>0]; neg=net[net<0]; eq=np.r_[0,np.cumsum(net)]; dd=eq-np.maximum.accumulate(eq)
    streak=mx=0
    for x in net:
        if x<0:streak+=1;mx=max(mx,streak)
        else:streak=0
    month=pd.Series(net).groupby(g.month.values).sum()
    pf=round(pos.sum()/abs(neg.sum()),3) if len(neg) and pos.sum()>0 else (float("inf") if len(pos) else 0.)
    return (len(g),round((net>0).mean()*100,2),pf,round(net.sum(),3),round(net.mean(),4),round(dd.min(),3),mx,round((month>0).mean(),3))
maxdiff=0
for _,r in summary.iterrows():
    g=trades[(trades.split==r.split)&(trades.variant==r.variant)]
    vals=independent(g,int(r.cost_bps))
    for col,val in zip(["trades","win_rate_pct","profit_factor","net_R","avg_R","max_drawdown_R","max_losing_streak","positive_month_fraction"],vals):
        actual=getattr(r,col)
        if pd.isna(val) and pd.isna(actual):continue
        diff=abs(float(actual)-float(val));maxdiff=max(maxdiff,diff);assert diff<0.0011,(r.variant,r.split,r.cost_bps,col,actual,val)
trades["signal_time"]=pd.to_datetime(trades.signal_time,utc=True)
trades["entry_time"]=pd.to_datetime(trades.entry_time,utc=True)
trades["exit_time"]=pd.to_datetime(trades.exit_time,utc=True)
assert (trades.exit_time>=trades.entry_time).all()
assert ((trades.exit_time-trades.entry_time)<=pd.Timedelta(minutes=55)).all()
assert (trades.entry_time>trades.signal_time).all()
for key,g in trades.groupby(["split","variant"]):
    g=g.sort_values("entry_time")
    assert (g.entry_time.iloc[1:].to_numpy()>g.exit_time.iloc[:-1].to_numpy()).all(),key
    assert ((g.signal_time.iloc[1:].reset_index(drop=True)-g.exit_time.iloc[:-1].reset_index(drop=True))>=pd.Timedelta(minutes=60)).all(),key
fund=trades[trades.exit_reason=="FUNDING_FLAT"]
for x in fund.exit_time+pd.Timedelta(minutes=5):
    assert x.hour in (0,8,16) and x.minute==0
rbps=trades.risk_points/trades.entry*10000
out={"summary_rows":len(summary),"trade_rows":len(trades),"independent_metric_max_abs_diff":maxdiff,
     "overlap_checks":"passed","cooldown_checks":"passed","funding_flat_trades":len(fund),
     "median_initial_risk_bps":float(rbps.median()),"p10_initial_risk_bps":float(rbps.quantile(.1)),
     "gate_pass_count":int(pd.read_csv(root/"candidate_gates.csv").gate_pass.sum()),
     "source_sha256":meta["source_sha256"],"oos_rows":int((summary.split=="oos").sum())}
(root/"independent_audit.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))
print("PASS: summary independently reconstructed; no overlap; cooldown, holding and funding-boundary checks passed.")
