#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
root=Path(__file__).parent
meta=json.loads((root/"metadata.json").read_text())
mat=pd.read_csv(root/"matrix.csv")
assert len(mat)==1152
gate=(mat.train_trades>=40)&(mat.train_profit_factor>=1.05)&(mat.train_net_R>0)&(mat.train_max_drawdown_R>=-25)&(mat.train_positive_month_fraction>=.5)
assert int(gate.sum())==0
assert int((mat.train_net_R>0).sum())==85
def metrics(path):
    d=pd.read_csv(root/path);r=d.net_R.to_numpy(float);pos=r[r>0];neg=r[r<0]
    eq=np.r_[0,np.cumsum(r)];dd=eq-np.maximum.accumulate(eq);streak=mx=0
    for x in r:
        if x<0:streak+=1;mx=max(mx,streak)
        else:streak=0
    d["entry_time"]=pd.to_datetime(d.entry_time,utc=True);d["exit_time"]=pd.to_datetime(d.exit_time,utc=True);d=d.sort_values("entry_time")
    no_overlap=(d.entry_time.iloc[1:].to_numpy()>d.exit_time.iloc[:-1].to_numpy()).all()
    return {"trades":len(r),"win_rate_pct":round((r>0).mean()*100,2),"profit_factor":round(pos.sum()/abs(neg.sum()),3) if len(neg) else None,
      "net_R":round(r.sum(),3),"max_drawdown_R":round(dd.min(),3),"max_losing_streak":mx,
      "max_hold_hours":float((d.exit_time-d.entry_time).dt.total_seconds().max()/3600),"no_overlap":bool(no_overlap)}
files=["best_train_train_trades.csv","best_train_validation_trades.csv","best_validation_min20_train_trades.csv","best_validation_min20_validation_trades.csv"]
aud={f:metrics(f) for f in files}
source=root/"BTCUSD_15m.csv";data=pd.read_csv(source,parse_dates=["timestamp"]);ts=pd.to_datetime(data.timestamp,utc=True)
gaps=int((ts.diff().dropna()!=pd.Timedelta(minutes=15)).sum())
invalid=int((~((data.high>=data[["open","close","low"]].max(axis=1))&(data.low<=data[["open","close","high"]].min(axis=1)))).sum())
sha=hashlib.sha256(source.read_bytes()).hexdigest()
assert gaps==0 and invalid==0 and sha==meta["dataset_sha256"]
out={"matrix_rows":len(mat),"train_gate_passes":int(gate.sum()),"positive_train_net_rows":int((mat.train_net_R>0).sum()),
 "metadata_train_eligible":meta["train_eligible"],"metadata_validation_passes":meta["validation_passes"],"oos_evaluated":meta["oos_evaluated"],
 "dataset_rows":len(data),"dataset_gaps":gaps,"invalid_ohlc_rows":invalid,"dataset_sha256":sha,"selected_trade_ledgers":aud}
(root/"independent_audit.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))
print("PASS: zero training gate passes; selected ledgers recalculated; dataset hash/continuity verified.")
