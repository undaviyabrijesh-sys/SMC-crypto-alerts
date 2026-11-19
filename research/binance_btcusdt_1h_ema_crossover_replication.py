#!/usr/bin/env python3
"""Frozen Binance BTCUSDT replication of the Delta EMA20/50 crossover."""
import argparse, hashlib, importlib.util, json, time
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
 kp=out/'BTCUSDT_5m.csv'
 if not kp.exists():
  cur=int(START.timestamp()*1000); end=int(DATA_END.timestamp()*1000); rows=[]
  while cur<end:
   stop=min(end-1,cur+(LIMIT-1)*M5_MS)
   x=api(s,K,{'symbol':SYMBOL,'interval':'5m','startTime':cur,'endTime':stop,'limit':LIMIT})
   if not x: break
   rows.extend(x); nxt=int(x[-1][0])+M5_MS
   if nxt<=cur: raise RuntimeError('Kline pagination stalled')
   cur=nxt; time.sleep(.08)
  if not rows: raise RuntimeError('No Binance klines')
  cols=['open_ms','open','high','low','close','volume','close_ms','qv','trades','tb','tq','ignore']
  d=pd.DataFrame(rows,columns=cols); d['timestamp']=pd.to_datetime(d.open_ms.astype('int64'),unit='ms',utc=True)
  d=d.loc[(d.timestamp>=START)&(d.timestamp<DATA_END),['timestamp','open','high','low','close','volume']]
  for c in ['open','high','low','close','volume']: d[c]=pd.to_numeric(d[c],errors='coerce')
  d=d.sort_values('timestamp').drop_duplicates('timestamp',keep='last'); d.to_csv(kp,index=False)
 fp=out/'BTCUSDT_funding.csv'
 if not fp.exists():
  cur=int(T0.timestamp()*1000); end=int(DATA_END.timestamp()*1000); rows=[]
  while cur<end:
   x=api(s,F,{'symbol':SYMBOL,'startTime':cur,'endTime':end-1,'limit':1000})
   if not x: break
   rows.extend(x); nxt=int(x[-1]['fundingTime'])+1
   if nxt<=cur: raise RuntimeError('Funding pagination stalled')
   cur=nxt
   if len(x)<1000: break
   time.sleep(.08)
  if not rows: raise RuntimeError('No funding records')
  f=pd.DataFrame(rows); f['timestamp']=pd.to_datetime(f.fundingTime.astype('int64'),unit='ms',utc=True)
  f['rate']=pd.to_numeric(f.fundingRate,errors='coerce'); f[['timestamp','rate']].sort_values('timestamp').drop_duplicates('timestamp').to_csv(fp,index=False)
 return kp,fp

def main():
 p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,default=Path('binance_btcusdt_ema_cross_results')); p.add_argument('--self-test',action='store_true'); a=p.parse_args()
 sp=importlib.util.spec_from_file_location('ema_base',BASE); base=importlib.util.module_from_spec(sp); sp.loader.exec_module(base)
 if a.self_test:
  base.self_test(); print('PASS frozen cross-exchange wrapper imports the audited Delta engine'); return
 kp,fp=download(a.out); f=pd.read_csv(fp,parse_dates=['timestamp']).sort_values('timestamp')
 if f.rate.isna().any() or not np.isfinite(f.rate.to_numpy(float)).all(): raise RuntimeError('Bad funding rates')
 f=f[(f.timestamp>=T0)&(f.timestamp<=DATA_END)]; dt=f.timestamp.diff().dropna().dt.total_seconds()/3600
 if len(f)<100 or (dt>12).any() or (dt<=0).any(): raise RuntimeError('Funding archive gap/non-monotonicity')
 ns=f.timestamp.astype('int64').to_numpy()
 def next_funding(ts):
  i=int(np.searchsorted(ns,pd.Timestamp(ts).value,side='right'))
  if i>=len(ns): raise RuntimeError('No next funding timestamp')
  return pd.Timestamp(ns[i],tz='UTC')
 base.DATA=kp; base.TRANSITION=T0; base.FUNDING_END=DATA_END; base.PAIRS=[(20,50)]
 base.ATR_MULTS=[1.5]; base.TARGETS=[3.0]; base.HTF_FILTERS=['none']; base.COSTS=COSTS; base.next_settlement=next_funding
 raw=base.load_5m(kp); h,_=base.build_features(raw); h=h[(h.index>=T0)&(h.index<DATA_END)].copy()
 events=base.build_events(h)[(20,50)]; di=int(h.index.searchsorted(DEV_END)); vi=int(h.index.searchsorted(VAL_END))
 cfg={'config_id':'ema20_50_atr1.5_tp3.0_none','pair':'20/50','atr_mult':1.5,'target_r':3.0,'htf_filter':'none'}
 dev=pd.DataFrame(base.simulate(h,events,dict(cfg,sample='development'),0,di)); val=pd.DataFrame(base.simulate(h,events,dict(cfg,sample='validation'),di,vi))
 trades=pd.concat([dev,val],ignore_index=True); trades.to_csv(a.out/'trades_dev_val.csv',index=False)
 summary=[]; monthly=[]; regimes=[]; sides=[]; costs=[]
 for name,g in [('development',dev),('validation',val)]:
  for b in COSTS: summary.append({'sample':name,'cost_bps':b,**base.metrics(g,f'net_R_{b}bp')})
  if len(g):
   for m,q in g.assign(month=g.entry_time.dt.strftime('%Y-%m')).groupby('month'): monthly.append({'sample':name,'month':m,**base.metrics(q,'net_R_10bp')})
   for r,q in g.groupby('regime'): regimes.append({'sample':name,'regime':r,**base.metrics(q,'net_R_10bp')})
   for side,q in g.groupby('side'): sides.append({'sample':name,'side':side,**base.metrics(q,'net_R_10bp')})
  for b in COSTS: costs.append({'sample':name,'cost_bps':b,'trades':len(g),'gross_R':float(g.gross_R.sum()) if len(g) else 0.,'net_R':float(g[f'net_R_{b}bp'].sum()) if len(g) else 0.})
 for name,rows in [('summary_dev_val_costs.csv',summary),('monthly_dev_val_10bps.csv',monthly),('regime_dev_val_10bps.csv',regimes),('side_dev_val_10bps.csv',sides),('cost_sensitivity.csv',costs)]: pd.DataFrame(rows).to_csv(a.out/name,index=False)
 overlap=sum(int(np.any((ns>pd.Timestamp(t.entry_time).value)&(ns<=pd.Timestamp(t.exit_time).value))) for t in trades.itertuples())
 if overlap: raise RuntimeError(f'{overlap} trades overlap funding')
 gaps=int((raw.index.to_series().diff().dropna()!=pd.Timedelta(minutes=5)).sum()); hg=int((h.index.to_series().diff().dropna()!=pd.Timedelta(hours=1)).sum())
 meta={'venue':'Binance USD-M BTCUSDT','source':'Binance 5m klines aggregated by frozen Delta engine','rows_5m':len(raw),'gaps_5m':gaps,'complete_1h_rows':len(h),'gaps_1h':hg,'start':str(raw.index.min()),'end':str(raw.index.max()),'development_end_exclusive':str(DEV_END),'validation_end_exclusive':str(VAL_END),'oos_evaluated':False,'data_buffer_end':str(DATA_END),'source_sha256':digest(kp),'funding_sha256':digest(fp),'funding_rows':len(f),'funding_intervals_hours':{str(float(k)):int(v) for k,v in dt.value_counts().sort_index().items()},'funding_overlap_trades':overlap,'funding_cashflow_applied':False,'config':cfg,'cost_bps':COSTS,'primary_cost_bps':PRIMARY,'delta_reference':{'development':{'trades':106,'win_rate_pct':41.51,'PF':.950,'net_R_10bps':-1.90,'max_DD_R':-11.32,'losing_streak':9},'validation':{'trades':27,'win_rate_pct':62.96,'PF':2.338,'net_R_10bps':7.99,'max_DD_R':-2.76,'losing_streak':5}},'limitations':['Single frozen config; no Binance tuning.','Overlapping dates: cross-exchange robustness, not temporal OOS.','No final OOS evaluation.','Actual funding timestamps used for safe exits; no funding cashflow.','Flat costs; no user fee tier/spread/slippage/impact/queue model.','1h OHLC ambiguity resolved stop-first.']}
 (a.out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 primary=pd.DataFrame(summary).query('cost_bps == 10')
 primary.to_csv(a.out/'primary_10bps.csv',index=False)
 report=['# Binance BTCUSDT 1H EMA20/50 cross-exchange replication','',
  '**Status:** completed historical replication; research only.','',
  '- Frozen rule: EMA20/50 completed 1H crossover, next-open entry, 1.5 × Wilder ATR14 stop, 3R target, no HTF filter. Both directions; one position at a time.',
  '- Funding: actual Binance fundingTime timestamps; positions exit at the last 1H close strictly before settlement. No funding cashflow is applied.',
  '- Costs: 4/7/10/20 bps round trip; 10 bps primary.',
  f'- Data: {len(raw):,} Binance 5m rows, {gaps} 5m gaps; {len(h):,} complete 1H rows, {hg} 1H gaps.',
  f'- Development ends {DEV_END}; validation ends {VAL_END}. Final OOS not evaluated.','',
  '| Split | Trades | Win rate | PF | Net R | Avg R | Max DD | Losing streak | Positive months |',
  '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for _,r in primary.iterrows():
  report.append(f"| {r['sample']} | {r['trades']} | {r['win_rate_pct']}% | {r['profit_factor']} | {r['net_R']}R | {r['avg_R']}R | {r['max_drawdown_R']}R | {r['max_losing_streak']} | {r['positive_months']}/{r['active_months']} |")
 report += ['', '| Split | 4 bps | 7 bps | 10 bps | 20 bps |','|---|---:|---:|---:|---:|']
 for sample in ['development','validation']:
  q={x['cost_bps']:x['net_R'] for x in costs if x['sample']==sample}
  report.append(f"| {sample} | {q[4]:.2f}R | {q[7]:.2f}R | {q[10]:.2f}R | {q[20]:.2f}R |")
 report += ['', 'Delta reference at 10 bps: development 106 trades / PF 0.950 / -1.90R; validation 27 trades / PF 2.338 / +7.99R. The Delta candidate failed its development gate.',
  'This is cross-exchange evidence on overlapping dates, not independent temporal OOS. No Binance parameter search was performed. See metadata and CSVs for monthly, regime, side and funding detail.']
 (a.out/'REPORT.md').write_text('\n'.join(report)+'\n')
 print(json.dumps(meta,indent=2)); print(primary.to_string(index=False))

if __name__=='__main__': main()
