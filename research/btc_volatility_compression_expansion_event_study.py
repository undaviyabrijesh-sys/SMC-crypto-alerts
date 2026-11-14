#!/usr/bin/env python3
"""BTC 15m realized-volatility compression -> expansion forward-return study.

Compression: 16-bar realized volatility is at/below its prior-only rolling
30-day 20th percentile. Trigger: next completed 15m bar has true range >=1.5x
the prior 16-bar median true range and closes beyond the prior 16-bar high/low.
Enter at next 15m open; one event per 8h cooldown. This is a signal event study,
not a stop/target strategy backtest.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR=pd.Timedelta(minutes=15)
RV_BARS=16
RV_LOOKBACK=2880
RV_MIN_PERIODS=1440
RV_QUANTILE=0.20
EXPANSION_MULT=1.5
COOLDOWN_BARS=32
HORIZONS={"1h":4,"4h":16,"8h":32}
COSTS_BPS=(6.0,12.0,20.0)
CONTROL_SEED=20261117
CONTROL_EXCLUSION_BARS=2
BOOTSTRAP_REPS=3000
BLOCK_LENGTH=7
PERIODS={
 "development":("2024-11-14","2025-11-14"),
 "validation":("2025-11-14","2026-05-14"),
 "final_holdout":("2026-05-14","2026-11-14"),
}
class StudyError(RuntimeError): pass

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""): h.update(block)
 return h.hexdigest()

def load_ohlcv(path:Path)->pd.DataFrame:
 d=pd.read_csv(path)
 if "timestamp" not in d: raise StudyError("missing timestamp")
 d["timestamp"]=pd.to_datetime(d.timestamp,utc=True,errors="raise")
 if d.timestamp.duplicated().any(): raise StudyError("duplicate timestamps")
 d=d.sort_values("timestamp").set_index("timestamp")
 for c in ("open","high","low","close"):
  d[c]=pd.to_numeric(d[c],errors="raise")
 if "volume" not in d: d["volume"]=0.0
 d["volume"]=pd.to_numeric(d.volume,errors="raise")
 a=d[["open","high","low","close","volume"]].to_numpy(float)
 if not np.isfinite(a).all() or (d[["open","high","low","close"]]<=0).any().any():
  raise StudyError("non-finite or non-positive OHLCV")
 bad=(d.high<d[["open","close","low"]].max(axis=1))|(d.low>d[["open","close","high"]].min(axis=1))
 if bad.any(): raise StudyError(f"invalid OHLC rows={int(bad.sum())}")
 if (d.volume<0).any(): raise StudyError("negative volume")
 d["segment"]=d.index.to_series().diff().ne(BAR).cumsum().astype(int)
 return d

def add_features(data:pd.DataFrame)->pd.DataFrame:
 d=data.copy()
 for col in ("tr","rv16","rv_q20","prior_tr_median","prior_high16","prior_low16"):
  d[col]=np.nan
 for col in ("compression","expansion","signal"):
  d[col]=False
 d["breakout_dir"]=0
 for _,g in d.groupby("segment",sort=False):
  prev=g.close.shift(1)
  tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
  logret=np.log(g.close).diff()
  rv=logret.rolling(RV_BARS,min_periods=RV_BARS).std(ddof=0)
  q=rv.rolling(RV_LOOKBACK,min_periods=RV_MIN_PERIODS).quantile(RV_QUANTILE).shift(1)
  med=tr.rolling(RV_BARS,min_periods=RV_BARS).median().shift(1)
  ph=g.high.rolling(RV_BARS,min_periods=RV_BARS).max().shift(1)
  pl=g.low.rolling(RV_BARS,min_periods=RV_BARS).min().shift(1)
  comp=rv.le(q)
  exp=tr.ge(EXPANSION_MULT*med)
  direction=pd.Series(np.select([g.close>ph,g.close<pl],[1,-1],default=0),index=g.index,dtype=int)
  sig=comp.shift(1,fill_value=False)&exp&(direction!=0)
  d.loc[g.index,"tr"]=tr
  d.loc[g.index,"rv16"]=rv
  d.loc[g.index,"rv_q20"]=q
  d.loc[g.index,"prior_tr_median"]=med
  d.loc[g.index,"prior_high16"]=ph
  d.loc[g.index,"prior_low16"]=pl
  d.loc[g.index,"compression"]=comp
  d.loc[g.index,"expansion"]=exp
  d.loc[g.index,"breakout_dir"]=direction
  d.loc[g.index,"signal"]=sig
 d["compression"]=d.compression.fillna(False).astype(bool)
 d["expansion"]=d.expansion.fillna(False).astype(bool)
 d["breakout_dir"]=d.breakout_dir.fillna(0).astype(int)
 d["signal"]=d.signal.fillna(False).astype(bool)
 return d

def completed_4h_regime(data:pd.DataFrame)->pd.Series:
 x=data.copy()
 h=x[["open","high","low","close"]].resample("4h",label="right",closed="left").agg(
  {"open":"first","high":"max","low":"min","close":"last"})
 count=x.close.resample("4h",label="right",closed="left").count()
 segs=x.segment.resample("4h",label="right",closed="left").nunique()
 h=h.loc[count.eq(16)&segs.eq(1)].dropna().copy()
 if h.empty: raise StudyError("no complete 4h candles")
 h["segment"]=h.index.to_series().diff().ne(pd.Timedelta(hours=4)).cumsum().to_numpy()
 h["ema50"]=h.groupby("segment").close.transform(lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean())
 h["ema200"]=h.groupby("segment").close.transform(lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
 bull=(h.close>h.ema50)&(h.ema50>h.ema200)
 bear=(h.close<h.ema50)&(h.ema50<h.ema200)
 h["regime"]=np.select([bull,bear],["bull","bear"],default="neutral")
 return h.regime.reindex(data.index,method="ffill").fillna("unavailable")

def build_events(d:pd.DataFrame,regime:pd.Series)->tuple[pd.DataFrame,set[int],set[int]]:
 rows=[]; last_signal=-10**9; event_indices=set(); expansion_breakout=set()
 idx=d.index
 for i in range(len(d)-1):
  if d.expansion.iloc[i] and d.breakout_dir.iloc[i]!=0:
   expansion_breakout.add(i)
  if not bool(d.signal.iloc[i]): continue
  if i-last_signal<=COOLDOWN_BARS: continue
  entry_i=i+1
  last_exit=entry_i+max(HORIZONS.values())-1
  if last_exit>=len(d) or d.segment.iloc[i:last_exit+1].nunique()!=1: continue
  side_sign=int(d.breakout_dir.iloc[i])
  entry_time=idx[entry_i]
  reg=str(regime.iloc[entry_i])
  rows.append({"event_id":len(rows),"signal_time":idx[i].isoformat(),
   "entry_time":entry_time.isoformat(),"day":str(idx[i].date()),
   "side":"long" if side_sign==1 else "short","side_sign":side_sign,
   "htf_regime":reg,"entry":float(d.open.iloc[entry_i]),
   "rv16":float(d.rv16.iloc[i]),"rv_q20":float(d.rv_q20.iloc[i]),
   "true_range":float(d.tr.iloc[i]),"prior_tr_median":float(d.prior_tr_median.iloc[i]),
   "breakout_level":float(d.prior_high16.iloc[i] if side_sign==1 else d.prior_low16.iloc[i])})
  event_indices.add(i); last_signal=i
 return pd.DataFrame(rows),event_indices,expansion_breakout

def build_controls(d:pd.DataFrame,events:pd.DataFrame,regime:pd.Series,
                   event_indices:set[int],expansion_breakout:set[int])->pd.DataFrame:
 rng=np.random.default_rng(CONTROL_SEED); used=set(); rows=[]
 for e in events.to_dict("records"):
  day=pd.Timestamp(e["day"],tz="UTC")
  start=d.index.searchsorted(day,side="left"); end=d.index.searchsorted(day+pd.Timedelta(days=1),side="left")
  sig_i=d.index.get_indexer([pd.Timestamp(e["signal_time"])])[0]
  bucket=pd.Timestamp(e["signal_time"]).hour//3
  candidates=[]
  for k in range(start,end-1):
   ts=d.index[k]
   if ts.hour//3!=bucket: continue
   if abs(k-sig_i)<=CONTROL_EXCLUSION_BARS: continue
   if k in event_indices or k in expansion_breakout or k in used: continue
   entry_i=k+1; last=entry_i+max(HORIZONS.values())-1
   if last>=len(d) or d.segment.iloc[k:last+1].nunique()!=1: continue
   if str(regime.iloc[entry_i])!=str(e["htf_regime"]): continue
   candidates.append(k)
  if not candidates: continue
  k=int(rng.choice(candidates)); used.add(k); entry_i=k+1
  rows.append({"event_id":int(e["event_id"]),"control_signal_time":d.index[k].isoformat(),
   "control_entry_time":d.index[entry_i].isoformat(),"day":e["day"],"side":e["side"],
   "side_sign":int(e["side_sign"]),"htf_regime":e["htf_regime"],
   "entry":float(d.open.iloc[entry_i]),"utc_3h_bucket":int(bucket)})
 return pd.DataFrame(rows)

def evaluate(d:pd.DataFrame,rows:pd.DataFrame,time_col:str)->pd.DataFrame:
 out=[]
 for r in rows.to_dict("records"):
  i=d.index.get_indexer([pd.Timestamp(r[time_col])])[0]
  if i<0: continue
  for horizon,bars in HORIZONS.items():
   j=i+bars-1
   if j>=len(d) or d.segment.iloc[i:j+1].nunique()!=1: continue
   gross=(float(d.close.iloc[j])/float(r["entry"])-1)*int(r["side_sign"])*100
   row={**r,"horizon":horizon,"exit_time":(d.index[j]+BAR).isoformat(),"gross_return_pct":gross}
   for bps in COSTS_BPS: row[f"net_{int(bps)}bps_pct"]=gross-bps/100
   out.append(row)
 return pd.DataFrame(out)

def block_ci(values:np.ndarray,seed:int)->list[float]|None:
 x=np.asarray(values,float); x=x[np.isfinite(x)]; n=len(x)
 if n<10: return None
 rng=np.random.default_rng(seed); blocks=int(np.ceil(n/BLOCK_LENGTH))
 starts=rng.integers(0,n,size=(BOOTSTRAP_REPS,blocks))
 ix=(starts[:,:,None]+np.arange(BLOCK_LENGTH)[None,None,:])%n
 sample=x[ix.reshape(BOOTSTRAP_REPS,-1)[:,:n]].mean(axis=1)
 return [round(float(v),6) for v in np.quantile(sample,[.025,.975])]

def paired_summary(events:pd.DataFrame,controls:pd.DataFrame,seed:int)->dict:
 out={}
 for h in HORIZONS:
  e=events[events.horizon==h]; c=controls[controls.horizon==h]
  p=e.merge(c[["event_id","gross_return_pct"]].rename(columns={"gross_return_pct":"control_gross_pct"}),on="event_id",how="inner")
  if p.empty: out[h]={"paired_n":0}; continue
  p=p.sort_values("entry_time"); gross=p.gross_return_pct.to_numpy(float); control=p.control_gross_pct.to_numpy(float)
  lift=gross-control
  month=pd.to_datetime(p.entry_time,utc=True).dt.tz_convert(None).dt.to_period("M")
  monthly=pd.DataFrame({"month":month,"net":gross-0.12}).groupby("month").net.mean()
  out[h]={"paired_n":int(len(p)),"event_mean_gross_pct":round(float(gross.mean()),5),
   "event_mean_net_6bps_pct":round(float((gross-.06).mean()),5),
   "event_mean_net_12bps_pct":round(float((gross-.12).mean()),5),
   "event_mean_net_20bps_pct":round(float((gross-.20).mean()),5),
   "control_mean_net_12bps_pct":round(float((control-.12).mean()),5),
   "paired_lift_pct":round(float(lift.mean()),5),
   "event_win_rate_net_12bps":round(float(((gross-.12)>0).mean()),4),
   "positive_month_fraction_net_12bps":round(float((monthly>0).mean()),4),
   "paired_lift_95pct_block_bootstrap_ci":block_ci(lift,seed+len(p)),
   "event_net_12bps_95pct_block_bootstrap_ci":block_ci(gross-.12,seed+2*len(p))}
 return out

def summarize(events:pd.DataFrame,event_returns:pd.DataFrame,control_returns:pd.DataFrame)->dict:
 result={}
 for period,(start,end) in PERIODS.items():
  lo=pd.Timestamp(start,tz="UTC"); hi=pd.Timestamp(end,tz="UTC")
  ids=set(events.loc[(pd.to_datetime(events.entry_time,utc=True)>=lo)&(pd.to_datetime(events.entry_time,utc=True)<hi),"event_id"].astype(int))
  result[period]={}
  for group in ("all","long","short"):
   selected=events if group=="all" else events[events.side==group]
   selected_ids=ids & set(selected.event_id.astype(int))
   result[period][group]=paired_summary(
    event_returns[event_returns.event_id.isin(selected_ids)],
    control_returns[control_returns.event_id.isin(selected_ids)],
    CONTROL_SEED+len(period)+len(group))
 return result

def self_test():
 assert int(np.select([101>100,101<90],[1,-1],default=0))==1
 assert int(np.select([89>100,89<90],[1,-1],default=0))==-1
 assert int(np.select([95>100,95<90],[1,-1],default=0))==0
 # Future-bar perturbations cannot change the already-computed feature at t.
 idx=pd.date_range("2026-01-01",periods=1700,freq="15min",tz="UTC")
 rng=np.random.default_rng(5); close=100*np.exp(np.cumsum(rng.normal(0,.001,1700)))
 d=pd.DataFrame({"open":close,"high":close*1.002,"low":close*.998,"close":close,"volume":1.0},index=idx)
 d["segment"]=0
 a=add_features(d)
 d2=d.copy(); d2.iloc[1601:,d2.columns.get_loc("close")]*=1.5
 d2.iloc[1601:,d2.columns.get_loc("high")]*=1.5
 d2.iloc[1601:,d2.columns.get_loc("low")]*=1.5
 d2.iloc[1601:,d2.columns.get_loc("open")]*=1.5
 b=add_features(d2)
 for col in ("rv16","rv_q20","prior_tr_median","prior_high16","prior_low16","compression","expansion","breakout_dir","signal"):
  av=a.iloc[1600][col]; bv=b.iloc[1600][col]
  if pd.isna(av): assert pd.isna(bv)
  elif isinstance(av,(bool,np.bool_)): assert av==bv
  else: assert abs(float(av)-float(bv))<1e-12
 print("PASS 4 deterministic compression/expansion tests")

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--csv",default="historical_data/BTC_15m.csv")
 ap.add_argument("--output-dir",default="results/btc-vol-expansion")
 ap.add_argument("--self-test",action="store_true")
 args=ap.parse_args()
 if args.self_test: self_test(); return
 path=Path(args.csv); d=load_ohlcv(path)
 if len(d)<30000: raise StudyError(f"insufficient BTC 15m history: {len(d)}")
 d=add_features(d); regime=completed_4h_regime(d)
 events,event_indices,expansion_breakout=build_events(d,regime)
 if events.empty: raise StudyError("no qualifying compression-expansion events")
 controls=build_controls(d,events,regime,event_indices,expansion_breakout)
 if controls.empty: raise StudyError("no matched controls")
 event_returns=evaluate(d,events,"entry_time")
 control_returns=evaluate(d,controls,"control_entry_time")
 if event_returns.empty or control_returns.empty: raise StudyError("no forward returns")
 out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
 events.to_csv(out/"events.csv",index=False); controls.to_csv(out/"matched_controls.csv",index=False)
 event_returns.to_csv(out/"event_forward_returns.csv",index=False)
 control_returns.to_csv(out/"control_forward_returns.csv",index=False)
 dif=d.index.to_series().diff().dropna()
 quality={"rows":int(len(d)),"start_utc":d.index.min().isoformat(),"end_utc":d.index.max().isoformat(),
  "gap_count":int((dif>BAR*1.5).sum()),"irregular_intervals":int((dif!=BAR).sum()),
  "zero_volume_rows":int((d.volume==0).sum()),"csv_sha256":sha256(path)}
 report={"status":"completed","symbol":"BTCUSD","timeframe":"15m","data_quality":quality,
  "data_hash_pandas_object_sha256":hashlib.sha256(pd.util.hash_pandas_object(d,index=True).values.tobytes()).hexdigest(),
  "event_count":int(len(events)),"matched_control_count":int(len(controls)),
  "control_match_rate":round(float(len(controls)/len(events)),4),
  "side_counts":events.side.value_counts().to_dict(),"regime_counts":events.htf_regime.value_counts().to_dict(),
  "rules":{"compression":"16-bar realized volatility <= prior-only rolling 30d 20th percentile (min 15d history)",
   "expansion":"current 15m true range >=1.5x prior 16-bar median true range",
   "breakout":"current close beyond prior 16-bar high/low (shifted one bar)",
   "entry":"next 15m open","cooldown_bars":COOLDOWN_BARS,"cooldown_hours":8,
   "forward_horizons_bars":HORIZONS,"control":"same UTC day, side, completed 4h regime and 3h UTC time bucket; non-expansion/non-event; outside +/-30m",
   "cost_sensitivity_round_trip_bps":COSTS_BPS},
  "bootstrap":{"method":"circular moving-block bootstrap on event-ordered paired observations",
   "block_length_observations":BLOCK_LENGTH,"replicates":BOOTSTRAP_REPS,"seed":CONTROL_SEED},
  "periods":summarize(events,event_returns,control_returns),
  "limitations":["Forward-return event study only; no stop/target PF, R or trade drawdown.",
   "Costs are sensitivities, not verified fees, spread or market impact.",
   "Funding is excluded; settlement mapping remains unverified.",
   "Matched controls are descriptive, not randomized causal controls.",
   "The final holdout is chronological and not used for parameter selection."]}
 (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
 print(json.dumps(report,indent=2))

if __name__=="__main__": main()
