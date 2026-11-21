#!/usr/bin/env python3
"""Reproducible BTC 1h EMA crossover research runner. Research only."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

PAIRS=[(9,21),(20,50),(50,200)]; ATRS=[1.5,2.5]; TARGETS=[2.0,3.0]
FILTERS=['none','4h_ema200']; COSTS=[4,7,10,20]
TRANSITION=pd.Timestamp('2025-09-08T12:00:00Z'); FUNDING_END=pd.Timestamp('2026-11-14T00:00:00Z')
H1=pd.Timedelta(hours=1); M5=pd.Timedelta(minutes=5)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def segids(idx,step): return idx.to_series().diff().ne(step).cumsum().astype(int)
def complete(d,rule,n,step):
 x=d.copy(); x['_s']=segids(x.index,step).to_numpy(); kw={'label':'right','closed':'left'}
 a=x[['open','high','low','close','volume']].resample(rule,**kw).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
 c=x.close.resample(rule,**kw).count(); s=x._s.resample(rule,**kw).nunique()
 z=a.loc[c.eq(n)&s.eq(1)].dropna(subset=['open','high','low','close']).copy()
 z['segment']=segids(z.index,pd.Timedelta(rule)).to_numpy()
 if 'segment' in d.columns: z['source_segment']=x.segment.resample(rule,**kw).first().reindex(z.index).astype(int)
 return z
def atr_wilder(d,n=14):
 out=pd.Series(np.nan,index=d.index,dtype=float)
 for _,g in d.groupby('segment',sort=False):
  p=g.close.shift(); tr=pd.concat([g.high-g.low,(g.high-p).abs(),(g.low-p).abs()],axis=1).max(axis=1).to_numpy(float)
  a=np.full(len(g),np.nan)
  if len(g)>=n and np.isfinite(tr[:n]).all():
   a[n-1]=tr[:n].mean()
   for i in range(n,len(g)): a[i]=(a[i-1]*(n-1)+tr[i])/n
  out.loc[g.index]=a
 return out
def features(raw):
 h=complete(raw,'1h',12,M5); h['atr14']=atr_wilder(h)
 for p in sorted(set(x for pair in PAIRS for x in pair)):
  h[f'ema{p}']=h.groupby('segment',sort=False).close.transform(lambda s:s.ewm(span=p,adjust=False,min_periods=p).mean())
 h4=complete(h,'4h',4,H1)
 h4['ema200']=h4.groupby('segment',sort=False).close.transform(lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
 h['h4_close']=h4.close.reindex(h.index,method='ffill'); h['h4_ema200']=h4.ema200.reindex(h.index,method='ffill')
 h['h4_source_segment']=h4.source_segment.reindex(h.index,method='ffill')
 ok=h.h4_source_segment.eq(h.segment); h.loc[~ok,['h4_close','h4_ema200']]=np.nan
 h['regime']=np.select([h.h4_close>h.h4_ema200,h.h4_close<h.h4_ema200],['bull','bear'],default='neutral_or_unavailable')
 return h,h4
def next_settle(t):
 t=pd.Timestamp(t); return t.normalize()+pd.Timedelta(hours=((t.hour//8)+1)*8)
def exit_fill(side,o,hi,lo,sl,tp):
 if side=='long':
  if o<=sl:return float(o),'SL_GAP'
  if o>=tp:return float(tp),'TP_GAP_CAPPED'
  s=lo<=sl; t=hi>=tp
 else:
  if o>=sl:return float(o),'SL_GAP'
  if o<=tp:return float(tp),'TP_GAP_CAPPED'
  s=hi>=sl; t=lo<=tp
 if s:return float(sl),'SL_AMBIGUOUS' if t else 'SL'
 if t:return float(tp),'TP'
 return None,None
def events(h):
 out={}
 for f,s in PAIRS:
  a=h[f'ema{f}'].to_numpy(float); b=h[f'ema{s}'].to_numpy(float); sg=h.segment.to_numpy(); z=[]
  for i in range(1,len(h)-1):
   if sg[i-1]!=sg[i] or sg[i+1]!=sg[i] or not np.isfinite([a[i-1],b[i-1],a[i],b[i],h.atr14.iloc[i]]).all():continue
   l=a[i-1]<=b[i-1] and a[i]>b[i]; sh=a[i-1]>=b[i-1] and a[i]<b[i]
   if l==sh:continue
   z.append((i,i+1,'long' if l else 'short',float(h.atr14.iloc[i]),float(h.close.iloc[i])))
  out[(f,s)]=z
 return out
def stats(g,col):
 if g.empty:return dict(trades=0,win_rate_pct=0,profit_factor=np.nan,net_R=0,avg_R=0,max_drawdown_R=0,max_losing_streak=0,positive_month_fraction=0,positive_months=0,active_months=0,TP=0,SL=0,TIME=0)
 g=g.sort_values('entry_time'); r=g[col].astype(float); w=r[r>0]; l=r[r<0]; eq=r.cumsum().to_numpy(); dd=eq-np.maximum.accumulate(np.r_[0.,eq])[1:]
 streak=mx=0
 for v in r: streak=streak+1 if v<0 else 0; mx=max(mx,streak)
 m=g.assign(m=g.entry_time.dt.strftime('%Y-%m')).groupby('m')[col].sum()
 return dict(trades=len(g),win_rate_pct=round((r>0).mean()*100,2),profit_factor=round(w.sum()/abs(l.sum()),3) if len(l) and abs(l.sum()) else np.nan,net_R=round(r.sum(),2),avg_R=round(r.mean(),3),max_drawdown_R=round(min(0,dd.min()),2),max_losing_streak=mx,positive_month_fraction=round((m>0).mean(),3),positive_months=int((m>0).sum()),active_months=len(m),TP=int(g.outcome.str.startswith('TP').sum()),SL=int(g.outcome.str.startswith('SL').sum()),TIME=int((g.outcome=='TIME').sum()))
def simulate(h,ev,cfg,start,end):
 ix=h.index; op=h.open.to_numpy(float); hi=h.high.to_numpy(float); lo=h.low.to_numpy(float); cl=h.close.to_numpy(float); sg=h.segment.to_numpy(); rows=[]; last=-1
 for si,ei,side,atr,sc in ev:
  if si<start or ei>=end or ei<=last:continue
  et=ix[si]
  if et<TRANSITION or et>=FUNDING_END:continue
  boundary=next_settle(et); max_t=boundary-H1; max_i=ix.searchsorted(max_t,side='right')-1
  if max_i<ei or max_i>=end or sg[ei]!=sg[si] or not np.all(sg[ei:max_i+1]==sg[ei]):continue
  if cfg['filter']=='4h_ema200':
   c=float(h.h4_close.iloc[si]); e=float(h.h4_ema200.iloc[si])
   if not np.isfinite([c,e]).all() or (side=='long' and c<=e) or (side=='short' and c>=e):continue
  entry=float(op[ei]); sl=sc-cfg['atr']*atr if side=='long' else sc+cfg['atr']*atr
  risk=entry-sl if side=='long' else sl-entry
  if not np.isfinite(risk) or risk<=0 or risk/entry>.08:continue
  tp=entry+cfg['target']*risk if side=='long' else entry-cfg['target']*risk
  out='TIME'; xi=max_i; xp=float(cl[xi])
  for k in range(ei,max_i+1):
   fill,reason=exit_fill(side,float(op[k]),float(hi[k]),float(lo[k]),sl,tp)
   if reason:xp=fill;xi=k;out=reason;break
  gross=(xp-entry)/risk if side=='long' else (entry-xp)/risk
  row=dict(config_id=cfg['config_id'],pair=cfg['pair'],atr_mult=cfg['atr'],target_r=cfg['target'],htf_filter=cfg['filter'],sample=cfg['sample'],side=side,regime=str(h.regime.iloc[si]),signal_time=ix[si],entry_time=et,exit_time=ix[xi],entry=entry,stop=sl,target=tp,exit=xp,risk=risk,outcome=out,gross_R=gross,bars_held=xi-ei+1,funding_boundary=boundary)
  for b in COSTS:row[f'net_R_{b}bp']=gross-(b/10000*entry/risk)
  rows.append(row);last=xi
 return rows
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--funding',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 raw=pd.read_csv(a.data);raw.timestamp=pd.to_datetime(raw.timestamp,utc=True);raw=raw.sort_values('timestamp').set_index('timestamp')
 if raw.index.duplicated().any():raise ValueError('duplicate 5m timestamps')
 if not np.isfinite(raw[['open','high','low','close','volume']].to_numpy(float)).all():raise ValueError('nonfinite source')
 if (raw[['open','high','low','close']]<=0).any().any() or (raw.volume<0).any():raise ValueError('nonpositive price or negative volume')
 bad=(raw.high<raw[['open','close','low']].max(axis=1))|(raw.low>raw[['open','close','high']].min(axis=1))
 if bad.any():raise ValueError(f'invalid OHLC rows={int(bad.sum())}')
 source_gaps=int((raw.index.to_series().diff().dropna()!=M5).sum()); raw['segment']=segids(raw.index,M5)
 f=pd.read_csv(a.funding);f.timestamp=pd.to_datetime(f.timestamp,utc=True);f=f.sort_values('timestamp').set_index('timestamp')
 post=f.loc[(f.index>=TRANSITION)&(f.index<=FUNDING_END)]; settle=post.loc[post.index.hour.isin([0,8,16])]
 expected=pd.date_range('2025-09-08T16:00:00Z',FUNDING_END,freq='8h'); missing_settlements=len(expected.difference(settle.index))
 if missing_settlements:raise ValueError('missing settlement timestamp')
 funding_hourly_gaps=int((post.index.to_series().diff().dropna()!=H1).sum())
 h,h4=features(raw);h=h.loc[(h.index>=TRANSITION)&(h.index<FUNDING_END)].copy();n=len(h);de=int(n*.70);ve=int(n*.85)
 ev=events(h);tr=[];sm=[];mo=[];rg=[]
 for f0,s0 in PAIRS:
  for atr in ATRS:
   for target in TARGETS:
    for filt in FILTERS:
     cfg0={'config_id':f'ema{f0}_{s0}_atr{atr}_tp{target}_{filt}','pair':f'{f0}/{s0}','atr':atr,'target':target,'filter':filt}
     for sample,st,en in [('development',0,de),('validation',de,ve)]:
      cfg=dict(cfg0,sample=sample);g=pd.DataFrame(simulate(h,ev[(f0,s0)],cfg,st,en))
      if len(g):tr.extend(g.to_dict('records'))
      for b in COSTS:sm.append({**cfg,'cost_bps':b,**stats(g,f'net_R_{b}bp')})
      if len(g):
       g['month']=g.entry_time.dt.strftime('%Y-%m')
       for m,q in g.groupby('month'):
        for b in COSTS:mo.append(dict(config_id=cfg['config_id'],sample=sample,month=m,cost_bps=b,trades=len(q),net_R=round(float(q[f'net_R_{b}bp'].sum()),4)))
       for r,q in g.groupby('regime'):
        for b in COSTS:rg.append(dict(config_id=cfg['config_id'],sample=sample,regime=r,cost_bps=b,trades=len(q),net_R=round(float(q[f'net_R_{b}bp'].sum()),4)))
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);pd.DataFrame(sm).to_csv(out/'summary_dev_val_costs.csv',index=False);pd.DataFrame(tr).to_csv(out/'trades_dev_val_10bps.csv',index=False);pd.DataFrame(mo).to_csv(out/'monthly_dev_val.csv',index=False);pd.DataFrame(rg).to_csv(out/'regime_dev_val.csv',index=False)
 pri=pd.DataFrame(sm);pri=pri[pri.cost_bps.eq(10)];d=pri[pri['sample'].eq('development')];v=pri[pri['sample'].eq('validation')];j=d.merge(v,on='config_id',suffixes=('_dev','_val'))
 j['pass_both']=(j.trades_dev>=50)&(j.trades_val>=20)&(j.net_R_dev>0)&(j.net_R_val>0)&(j.profit_factor_dev>1.10)&(j.profit_factor_val>1.10)&(j.positive_month_fraction_dev>=.5)&(j.positive_month_fraction_val>=.5)&(j.max_drawdown_R_dev>=-20)&(j.max_drawdown_R_val>=-10);j.to_csv(out/'paired_gates_10bps.csv',index=False)
 meta={'source_5m_rows':len(raw),'source_5m_gaps':source_gaps,'invalid_ohlc_rows':int(bad.sum()),'source_sha256':sha(a.data),'funding_sha256':sha(a.funding),'eval_rows':n,'eval_start':str(h.index.min()),'eval_end_exclusive':str(FUNDING_END),'development_rows':de,'validation_rows':ve-de,'oos_reserved_rows':n-ve,'development_end_exclusive':str(h.index[de]),'validation_end_exclusive':str(h.index[ve]),'configurations':24,'summary_rows':len(sm),'trade_rows_10bps':len(tr),'funding_post_hourly_gaps':funding_hourly_gaps,'funding_settlement_rows':len(settle),'missing_settlement_rows':missing_settlements,'h4_complete_rows':len(h4),'funding_cashflow_applied':False,'funding_safe_exit':'exit at last hourly close strictly before next 00/08/16 UTC settlement','oos_evaluated':False,'pass_both':int(j.pass_both.sum())}
 (out/'metadata.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2));print('TOP DEV',d.sort_values('net_R',ascending=False).head(5).to_string(index=False));print('TOP VAL',v.sort_values('net_R',ascending=False).head(5).to_string(index=False))
if __name__=='__main__':main()
