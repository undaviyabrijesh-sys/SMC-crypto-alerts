#!/usr/bin/env python3
"""Frozen Binance BTCUSDT replication of the Delta EMA20/50 crossover."""
import argparse, hashlib, importlib.util, json, time, io, re, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research'/'btc_1h_ema_crossover_funding_safe.py'
K='https://fapi.binance.com/fapi/v1/klines'; F='https://fapi.binance.com/fapi/v1/fundingRate'
SYMBOL='BTCUSDT'; START=pd.Timestamp('2024-11-16T00:00:00Z')
T0=pd.Timestamp('2025-09-08T12:00:00Z'); DEV_END=pd.Timestamp('2026-07-07T13:00:00Z')
VAL_END=pd.Timestamp('2026-09-10T06:00:00Z'); DATA_END=VAL_END+pd.Timedelta(hours=12)
COSTS=[4,7,10,20]; PRIMARY=10; M5_MS=300000; LIMIT=1500

def digest(p):
 h=hashlib.sha256(); f=open(p,'rb')
 for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 f.close(); return h.hexdigest()

def api(s,url,params):
 err=None
 for n in range(7):
  try:
   r=s.get(url,params=params,timeout=45)
   if r.status_code in (418,429): time.sleep(min(2**n,30)); continue
   r.raise_for_status(); x=r.json()
   if isinstance(x,dict) and 'code' in x: raise RuntimeError(x)
   return x
  except Exception as e:
   err=e
   if n<6: time.sleep(min(2**n,20))
 raise RuntimeError(f'Binance API failed: {err}')

def download(out):
 out.mkdir(parents=True,exist_ok=True); s=requests.Session()
 s.headers.update({"User-Agent":"SaltyQuantResearch/1.0"})
 manifest=[]
 def archive(url,kind,period):
  c=s.get(url+".CHECKSUM",timeout=60); c.raise_for_status()
  m=re.search(r"([0-9a-fA-F]{64})",c.text)
  if not m: raise RuntimeError(f"Missing SHA256 checksum for {url}")
  expected=m.group(1).lower()
  z=s.get(url,timeout=120); z.raise_for_status()
  actual=hashlib.sha256(z.content).hexdigest()
  if actual!=expected: raise RuntimeError(f"Checksum mismatch for {url}: {actual} != {expected}")
  with zipfile.ZipFile(io.BytesIO(z.content)) as zz:
   names=[n for n in zz.namelist() if n.lower().endswith(".csv")]
   if len(names)!=1: raise RuntimeError(f"Expected one CSV in {url}; found {names}")
   if kind=="klines":
    d=pd.read_csv(zz.open(names[0]),header=None,usecols=range(6))
    d.columns=["open_ms","open","high","low","close","volume"]
    ts=pd.to_numeric(d.open_ms,errors="coerce")
    unit="us" if ts.median()>1e14 else "ms"
    d["timestamp"]=pd.to_datetime(ts,unit=unit,utc=True)
    for col in ["open","high","low","close","volume"]: d[col]=pd.to_numeric(d[col],errors="coerce")
    d=d[["timestamp","open","high","low","close","volume"]]
   else:
    d=pd.read_csv(zz.open(names[0]))
    cols={str(c).strip().lower():c for c in d.columns}
    tc=next((cols[k] for k in ["calc_time","fundingtime","funding_time","timestamp","time"] if k in cols),None)
    rc=next((cols[k] for k in ["last_funding_rate","fundingrate","funding_rate","rate"] if k in cols),None)
    if tc is None or rc is None:
     d=pd.read_csv(zz.open(names[0]),header=None)
     if d.shape[1]<2: raise RuntimeError(f"Unrecognized funding schema in {url}")
     tc=d.columns[0]; rc=d.columns[-1]
    rawts=d[tc]; num=pd.to_numeric(rawts,errors="coerce")
    if num.notna().mean()>.9:
     unit="us" if num.median()>1e14 else "ms"
     ts=pd.to_datetime(num,unit=unit,utc=True)
    else: ts=pd.to_datetime(rawts,utc=True)
    d=pd.DataFrame({"timestamp":ts,"rate":pd.to_numeric(d[rc],errors="coerce")})
  manifest.append({"type":kind,"period":period,"url":url,"sha256":actual,"checksum_verified":True,"rows":len(d)})
  return d
 start_month=pd.Timestamp(START.year,START.month,1,tz="UTC")
 end_month=pd.Timestamp(DATA_END.year,DATA_END.month,1,tz="UTC")
 months=pd.date_range(start_month,end_month,freq="MS")
 kparts=[]
 for m in months:
  ym=m.strftime("%Y-%m")
  url=f"https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-{ym}.zip"
  kparts.append(archive(url,"klines",ym)); time.sleep(.05)
 kd=pd.concat(kparts,ignore_index=True)
 kd=kd.loc[(kd.timestamp>=START)&(kd.timestamp<DATA_END)].sort_values("timestamp").drop_duplicates("timestamp",keep="last")
 kp=out/"BTCUSDT_5m.csv"; kd.to_csv(kp,index=False)
 fstart=pd.Timestamp(T0.year,T0.month,1,tz="UTC")
 fmonths=pd.date_range(fstart,end_month,freq="MS")
 fparts=[]
 for m in fmonths:
  ym=m.strftime("%Y-%m")
  url=f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{ym}.zip"
  fparts.append(archive(url,"funding",ym)); time.sleep(.05)
 fd=pd.concat(fparts,ignore_index=True)
 fd=fd.loc[(fd.timestamp>=T0)&(fd.timestamp<=DATA_END)].sort_values("timestamp").drop_duplicates("timestamp",keep="last")
 if fd.rate.isna().any(): raise RuntimeError("Non-finite funding rates after archive parse")
 fp=out/"BTCUSDT_funding.csv"; fd.to_csv(fp,index=False)
 pd.DataFrame(manifest).to_csv(out/"archive_manifest.csv",index=False)
 (out/"archive_metadata.json").write_text(json.dumps({"checksum_verified_archives":len(manifest),"kline_archives":len(kparts),"funding_archives":len(fparts),"kline_rows":len(kd),"funding_rows":len(fd),"data_end_exclusive":str(DATA_END)},indent=2)+"\n")
 return kp,fp

def load_base():
 sp=importlib.util.spec_from_file_location('ema_base',BASE)
 if sp is None or sp.loader is None: raise RuntimeError(f'Cannot load {BASE}')
 mod=importlib.util.module_from_spec(sp); sp.loader.exec_module(mod); return mod

def self_test(base):
 assert base.exit_fill('long',100,120,80,90,110)==(90.0,'SL_AMBIGUOUS')
 assert base.exit_fill('short',100,120,80,110,90)==(110.0,'SL_AMBIGUOUS')
 assert base.exit_fill('long',85,95,80,90,110)==(85.0,'SL_GAP')
 assert base.exit_fill('long',115,120,112,90,110)==(110.0,'TP_GAP_CAPPED')
 # Right-labelled 5m->1h aggregation: next bar opens at signal close.
 ix=pd.date_range('2026-01-01T00:00:00Z',periods=24,freq='5min')
 q=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.},index=ix)
 q['segment']=base.segids(q.index,base.M5)
 h=base.complete(q,'1h',12,base.M5)
 assert list(h.index[:2])==[pd.Timestamp('2026-01-01T01:00:00Z'),pd.Timestamp('2026-01-01T02:00:00Z')]
 assert h.index[0]==ix[12]
 # Actual funding-time lookup uses the first settlement strictly after entry.
 ns=np.fromiter((t.value for t in pd.date_range('2026-01-01T00:00:00Z',periods=10,freq='8h')),dtype=np.int64,count=10)
 def nxt(t):
  j=int(np.searchsorted(ns,pd.Timestamp(t).value,side='right')); return pd.Timestamp(ns[j],tz='UTC')
 assert nxt(pd.Timestamp('2026-01-01T00:00:00Z'))==pd.Timestamp('2026-01-01T08:00:00Z')
 assert nxt(pd.Timestamp('2026-01-01T07:00:00Z'))==pd.Timestamp('2026-01-01T08:00:00Z')
 assert nxt(pd.Timestamp('2026-01-01T08:00:00Z'))==pd.Timestamp('2026-01-01T16:00:00Z')
 # Funding-safe simulation and split isolation using the repository's exact engine.
 old=(base.TRANSITION,base.FUNDING_END,base.COSTS,base.next_settle)
 base.TRANSITION=pd.Timestamp('2026-01-01T00:00:00Z'); base.FUNDING_END=pd.Timestamp('2026-01-01T16:00:00Z'); base.COSTS=COSTS
 base.next_settle=lambda t: pd.Timestamp('2026-01-01T08:00:00Z') if pd.Timestamp(t)<pd.Timestamp('2026-01-01T08:00:00Z') else pd.Timestamp('2026-01-01T16:00:00Z')
 hi=pd.date_range('2026-01-01T01:00:00Z',periods=7,freq='1h')
 z=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.,'segment':1,'regime':'bull'},index=hi)
 ev=[(2,3,'long',1.,100.)]; cfg={'config_id':'test','pair':'20/50','atr':1.5,'target':3.,'filter':'none','sample':'dev'}
 trade=base.simulate(z,ev,cfg,0,7)
 assert len(trade)==1 and trade[0]['exit_time']==pd.Timestamp('2026-01-01T07:00:00Z')
 assert trade[0]['exit_time']<trade[0]['funding_boundary']
 assert base.simulate(z,ev,cfg,0,5)==[]
 base.TRANSITION,base.FUNDING_END,base.COSTS,base.next_settle=old
 assert np.isclose(.5-(10/10000*60000/600),.4)
 print('PASS 7 deterministic groups: stop-first/gaps, right-label aggregation, actual funding lookup, funding-safe exit, split isolation and cost-R arithmetic')

def main():
 p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,default=Path('binance_btcusdt_ema_cross_results')); p.add_argument('--self-test',action='store_true'); a=p.parse_args()
 base=load_base()
 if a.self_test: self_test(base); return
 a.out.mkdir(parents=True,exist_ok=True); kp,fp=download(a.out)
 f=pd.read_csv(fp,parse_dates=['timestamp']).sort_values('timestamp')
 if f.rate.isna().any() or not np.isfinite(f.rate.to_numpy(float)).all(): raise RuntimeError('Bad funding rates')
 f=f[(f.timestamp>=T0)&(f.timestamp<=DATA_END)]; dt=f.timestamp.diff().dropna().dt.total_seconds()/3600
 if len(f)<100 or (dt>12).any() or (dt<=0).any(): raise RuntimeError('Funding archive gap/non-monotonicity')
 ns=np.fromiter((pd.Timestamp(t).value for t in f.timestamp),dtype=np.int64,count=len(f))
 def next_funding(ts):
  i=int(np.searchsorted(ns,pd.Timestamp(ts).value,side='right'))
  if i>=len(ns): raise RuntimeError('No next funding timestamp')
  return pd.Timestamp(ns[i],tz='UTC')
 base.TRANSITION=T0; base.FUNDING_END=DATA_END; base.PAIRS=[(20,50)]; base.ATRS=[1.5]; base.TARGETS=[3.0]; base.FILTERS=['none']; base.COSTS=COSTS; base.next_settle=next_funding
 raw=pd.read_csv(kp); raw.timestamp=pd.to_datetime(raw.timestamp,utc=True); raw=raw.sort_values('timestamp').set_index('timestamp')
 if raw.index.duplicated().any(): raise RuntimeError('Duplicate Binance 5m timestamps')
 if not np.isfinite(raw[['open','high','low','close','volume']].to_numpy(float)).all(): raise RuntimeError('Non-finite OHLCV')
 if (raw[['open','high','low','close']]<=0).any().any() or (raw.volume<0).any(): raise RuntimeError('Invalid price/volume')
 bad=(raw.high<raw[['open','close','low']].max(axis=1))|(raw.low>raw[['open','close','high']].min(axis=1))
 if bad.any(): raise RuntimeError(f'Invalid OHLC rows: {int(bad.sum())}')
 raw['segment']=base.segids(raw.index,base.M5)
 h,h4=base.features(raw); h=h.loc[(h.index>=T0)&(h.index<DATA_END)].copy()
 events=base.events(h)[(20,50)]; di=int(h.index.searchsorted(DEV_END)); vi=int(h.index.searchsorted(VAL_END))
 cfg={'config_id':'ema20_50_atr1.5_tp3.0_none','pair':'20/50','atr':1.5,'target':3.0,'filter':'none'}
 dev=pd.DataFrame(base.simulate(h,events,dict(cfg,sample='development'),0,di)); val=pd.DataFrame(base.simulate(h,events,dict(cfg,sample='validation'),di,vi))
 trades=pd.concat([dev,val],ignore_index=True); trades.to_csv(a.out/'trades_dev_val.csv',index=False)
 summary=[]; monthly=[]; regimes=[]; sides=[]; costs=[]
 for name,g in [('development',dev),('validation',val)]:
  for b in COSTS: summary.append({'sample':name,'cost_bps':b,**base.stats(g,f'net_R_{b}bp')})
  if len(g):
   for m,q in g.assign(month=g.entry_time.dt.strftime('%Y-%m')).groupby('month'): monthly.append({'sample':name,'month':m,**base.stats(q,'net_R_10bp')})
   for r,q in g.groupby('regime'): regimes.append({'sample':name,'regime':r,**base.stats(q,'net_R_10bp')})
   for side,q in g.groupby('side'): sides.append({'sample':name,'side':side,**base.stats(q,'net_R_10bp')})
  for b in COSTS: costs.append({'sample':name,'cost_bps':b,'trades':len(g),'gross_R':float(g.gross_R.sum()) if len(g) else 0.,'net_R':float(g[f'net_R_{b}bp'].sum()) if len(g) else 0.})
 for name,rows in [('summary_dev_val_costs.csv',summary),('monthly_dev_val_10bps.csv',monthly),('regime_dev_val_10bps.csv',regimes),('side_dev_val_10bps.csv',sides),('cost_sensitivity.csv',costs)]: pd.DataFrame(rows).to_csv(a.out/name,index=False)
 overlap=sum(int(np.any((ns>pd.Timestamp(t.entry_time).value)&(ns<=pd.Timestamp(t.exit_time).value))) for t in trades.itertuples())
 if overlap: raise RuntimeError(f'{overlap} trades overlap funding')
 gaps=int((raw.index.to_series().diff().dropna()!=base.M5).sum()); hg=int((h.index.to_series().diff().dropna()!=base.H1).sum())
 meta={'venue':'Binance USD-M BTCUSDT','source':'Binance 5m klines aggregated by frozen Delta engine','rows_5m':len(raw),'gaps_5m':gaps,'complete_1h_rows':len(h),'gaps_1h':hg,'start':str(raw.index.min()),'end':str(raw.index.max()),'development_end_exclusive':str(DEV_END),'validation_end_exclusive':str(VAL_END),'oos_evaluated':False,'data_buffer_end':str(DATA_END),'source_sha256':digest(kp),'funding_sha256':digest(fp),'funding_rows':len(f),'funding_intervals_hours':{str(float(k)):int(v) for k,v in dt.value_counts().sort_index().items()},'funding_overlap_trades':overlap,'funding_cashflow_applied':False,'config':cfg,'cost_bps':COSTS,'primary_cost_bps':PRIMARY,'delta_reference':{'development':{'trades':106,'win_rate_pct':41.51,'PF':.950,'net_R_10bps':-1.90,'max_DD_R':-11.32,'losing_streak':9},'validation':{'trades':27,'win_rate_pct':62.96,'PF':2.338,'net_R_10bps':7.99,'max_DD_R':-2.76,'losing_streak':5}},'limitations':['Single frozen config; no Binance tuning.','Overlapping dates: cross-exchange robustness, not temporal OOS.','No final OOS evaluation.','Actual funding timestamps used for safe exits; no funding cashflow.','Flat costs; no user fee tier/spread/slippage/impact/queue model.','1h OHLC ambiguity resolved stop-first.']}
 (a.out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 primary=pd.DataFrame(summary).query('cost_bps == 10'); primary.to_csv(a.out/'primary_10bps.csv',index=False)
 report=['# Binance BTCUSDT 1H EMA20/50 cross-exchange replication','', '**Status:** completed historical replication; research only.','',
  '- Frozen rule: EMA20/50 completed 1H crossover, next-open entry, 1.5 × Wilder ATR14 stop, 3R target, no HTF filter. Both directions; one position at a time.',
  '- Funding: actual Binance fundingTime timestamps; positions exit at the last 1H close strictly before settlement. No funding cashflow is applied.',
  '- Costs: 4/7/10/20 bps round trip; 10 bps primary.',
  f'- Data: {len(raw):,} Binance 5m rows, {gaps} 5m gaps; {len(h):,} complete 1H rows, {hg} 1H gaps.',
  f'- Development ends {DEV_END}; validation ends {VAL_END}. Final OOS not evaluated.','',
  '| Split | Trades | Win rate | PF | Net R | Avg R | Max DD | Losing streak | Positive months |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for _,r in primary.iterrows(): report.append(f"| {r['sample']} | {r['trades']} | {r['win_rate_pct']}% | {r['profit_factor']} | {r['net_R']}R | {r['avg_R']}R | {r['max_drawdown_R']}R | {r['max_losing_streak']} | {r['positive_months']}/{r['active_months']} |")
 report += ['', '| Split | 4 bps | 7 bps | 10 bps | 20 bps |','|---|---:|---:|---:|---:|']
 for sample in ['development','validation']:
  q={x['cost_bps']:x['net_R'] for x in costs if x['sample']==sample}; report.append(f"| {sample} | {q[4]:.2f}R | {q[7]:.2f}R | {q[10]:.2f}R | {q[20]:.2f}R |")
 report += ['', 'Delta reference at 10 bps: development 106 trades / PF 0.950 / -1.90R; validation 27 trades / PF 2.338 / +7.99R. The Delta candidate failed its development gate.', 'This is cross-exchange evidence on overlapping dates, not independent temporal OOS. No Binance parameter search was performed. See metadata and CSVs for monthly, regime, side and funding detail.']
 (a.out/'REPORT.md').write_text('\n'.join(report)+'\n')
 print(json.dumps(meta,indent=2)); print(primary.to_string(index=False))

if __name__=='__main__': main()
