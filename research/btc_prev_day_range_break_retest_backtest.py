from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

API='https://api.india.delta.exchange/v2/history/candles'
SYMBOL='BTCUSD'; DAYS=730; BAR=pd.Timedelta(minutes=5)
COSTS=(6,12,20); TARGETS=(1.5,2.0,3.0); MAX_HOLD=48

def digest(df):
    h=hashlib.sha256()
    for i in range(0,len(df),100000): h.update(df.iloc[i:i+100000].to_csv().encode())
    return h.hexdigest()

def normalize(raw):
    n=len(raw); d=raw.copy()
    if 'timestamp' not in d:
        d['timestamp']=pd.to_datetime(pd.to_numeric(d.pop('time'),errors='coerce'),unit='s',utc=True)
    elif pd.api.types.is_numeric_dtype(d.timestamp):
        d['timestamp']=pd.to_datetime(pd.to_numeric(d.timestamp,errors='coerce'),unit='s',utc=True)
    else: d['timestamp']=pd.to_datetime(d.timestamp,utc=True,errors='coerce')
    badts=int(d.timestamp.isna().sum()); d=d.dropna(subset=['timestamp'])
    dup=int(d.timestamp.duplicated().sum()); d=d.drop_duplicates('timestamp',keep='last').sort_values('timestamp').set_index('timestamp')
    missing=int(d.volume.isna().sum()) if 'volume' in d else len(d)
    if 'volume' not in d: d['volume']=0.
    d['volume']=pd.to_numeric(d.volume,errors='coerce').fillna(0.)
    for c in ('open','high','low','close'): d[c]=pd.to_numeric(d[c],errors='coerce')
    a=d[['open','high','low','close']].to_numpy(float); finite=np.isfinite(a).all(1)
    positive=(d[['open','high','low','close']]>0).all(axis=1).to_numpy()
    shape=((d.high>=d[['open','close','low']].max(axis=1))&(d.low<=d[['open','close','high']].min(axis=1))).to_numpy()
    badnf=int((~finite).sum()); badpos=int((finite&~positive).sum()); badshape=int((finite&positive&~shape).sum())
    d=d.loc[finite&positive&shape,['open','high','low','close','volume']]
    d=d[d.index+BAR<=pd.Timestamp.now(tz='UTC')]
    if d.empty: raise RuntimeError('No valid closed BTC 5m candles')
    delta=d.index.to_series().diff().dropna()
    meta={'source_rows':n,'valid_rows':len(d),'start_utc':d.index.min().isoformat(),'end_utc':d.index.max().isoformat(),
          'duplicates_removed':dup,'invalid_timestamps':badts,'invalid_nonfinite_ohlc':badnf,
          'invalid_nonpositive_ohlc':badpos,'invalid_ohlc_shape':badshape,'missing_volume':missing,
          'zero_volume_bars':int((d.volume==0).sum()),'gap_count':int((delta!=BAR).sum()),
          'largest_gap_minutes':float(delta.max().total_seconds()/60) if len(delta) else 0.,'sha256':digest(d)}
    return d,meta

def fetch():
    end=int(pd.Timestamp.now(tz='UTC').timestamp()); cur=end-DAYS*86400; frames=[]; total=0
    while cur<end:
        stop=min(cur+1800*300,end)
        r=requests.get(API,params={'resolution':'5m','symbol':SYMBOL,'start':cur,'end':stop},
                       headers={'Accept':'application/json','User-Agent':'SaltyQuant-PDRT/1.0'},timeout=45)
        r.raise_for_status(); p=r.json()
        if p.get('success') is not True: raise RuntimeError(f'Delta API error: {p}')
        rows=p.get('result') or []
        if rows: frames.append(pd.DataFrame(rows)); total+=len(rows)
        cur=stop; time.sleep(.08)
    if not frames: raise RuntimeError('Delta returned no BTC 5m candles')
    d,m=normalize(pd.concat(frames,ignore_index=True)); m['source_rows']=total
    return d,m

def segments(d):
    z=d.copy(); z['seg']=z.index.to_series().diff().ne(BAR).cumsum().astype(int); return z

def aggregate(d,rule,count):
    kw={'label':'right','closed':'left'}; cols=['open','high','low','close','volume']
    z=d[cols].resample(rule,**kw).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    n=d.close.resample(rule,**kw).count(); s=d.seg.resample(rule,**kw).nunique()
    z=z.loc[n.eq(count)&s.eq(1)].dropna(subset=cols[:4]).copy()
    z['seg']=z.index.to_series().diff().ne(pd.Timedelta(rule)).cumsum().astype(int)
    return z

def atr_prior(f,n=14):
    pc=f.groupby('seg').close.shift(1)
    tr=pd.concat([f.high-f.low,(f.high-pc).abs(),(f.low-pc).abs()],axis=1).max(axis=1)
    return tr.groupby(f.seg).transform(lambda s:s.ewm(alpha=1/n,adjust=False,min_periods=n).mean().shift(1))

def features(raw):
    d=segments(raw); d['atr5_prior']=atr_prior(d)
    daily=d[['open','high','low','close','volume','seg']].resample('1D',label='right',closed='left').agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum','seg':'nunique'})
    cnt=d.close.resample('1D',label='right',closed='left').count()
    daily=daily.loc[cnt.eq(288)&daily.seg.eq(1)].copy()
    # Right-labelled daily bar at midnight is the prior UTC day's completed range.
    ph=daily.high; pl=daily.low
    d['prior_day_high']=ph.reindex(d.index.floor('D')).to_numpy()
    d['prior_day_low']=pl.reindex(d.index.floor('D')).to_numpy()
    m15=aggregate(d,'15min',3); m15['atr15_prior']=atr_prior(m15)
    m15['prior_day_high']=ph.reindex(m15.index.floor('D')).to_numpy()
    m15['prior_day_low']=pl.reindex(m15.index.floor('D')).to_numpy()
    h4=aggregate(d,'4h',48)
    h4['e50']=h4.groupby('seg').close.transform(lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean())
    h4['e200']=h4.groupby('seg').close.transform(lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
    bull=(h4.close>h4.e50)&(h4.e50>h4.e200); bear=(h4.close<h4.e50)&(h4.e50<h4.e200)
    h4['regime']=np.select([bull,bear],['bull','bear'],default='neutral')
    d['regime']=h4.regime.reindex(d.index,method='ffill').fillna('neutral')
    meta={'valid_15m_bars':len(m15),'valid_4h_bars':len(h4),'complete_prior_utc_days':len(daily),
          'days_without_complete_prior_range':int(d.index.floor('D').nunique()-d.prior_day_high.groupby(d.index.floor('D')).first().notna().sum())}
    return d,m15,meta

def candidates(d,m15):
    pos={t:i for i,t in enumerate(d.index)}; out=[]; used=set()
    for t,b in m15.iterrows():
        if not np.isfinite(b.atr15_prior) or not np.isfinite(b.prior_day_high) or not np.isfinite(b.prior_day_low): continue
        up=b.close>=b.prior_day_high+.10*b.atr15_prior
        dn=b.close<=b.prior_day_low-.10*b.atr15_prior
        if bool(up)==bool(dn): continue
        side='long' if up else 'short'; day=t.floor('D').date().isoformat(); key=(day,side)
        if key in used or t not in pos: continue
        start=pos[t]; last=start-1
        if last<0 or d.seg.iloc[last]!=d.seg.iloc[start]: continue
        level=float(b.prior_day_high if up else b.prior_day_low); seg=int(d.seg.iloc[start]); found=None
        for k in range(start,min(start+12,len(d))):
            if int(d.seg.iloc[k])!=seg: break
            c=d.iloc[k]
            if (side=='long' and c.close<=level) or (side=='short' and c.close>=level): break
            a=c.atr5_prior
            if not np.isfinite(a) or a<=0: continue
            tol=.15*float(a); loc=(c.close-c.low)/max(c.high-c.low,1e-12)
            if side=='long':
                if c.low<level-tol: break
                touch=c.low<=level+tol
                hold=c.close>level and loc>=.5
            else:
                if c.high>level+tol: break
                touch=c.high>=level-tol
                hold=c.close<level and loc<=.5
            if touch and hold:
                ei=k+1
                if ei>=len(d) or int(d.seg.iloc[ei])!=seg: break
                entry=float(d.open.iloc[ei])
                if (side=='long' and entry<=level) or (side=='short' and entry>=level): break
                stop=float(c.low-.10*a) if side=='long' else float(c.high+.10*a)
                risk=entry-stop if side=='long' else stop-entry
                if not np.isfinite(risk) or risk<=0 or risk>2.5*a: break
                found={'break_time':t,'break_last_i':last,'retest_time':d.index[k],'retest_i':k,
                       'entry_time':d.index[ei],'entry_i':ei,'side':side,'day':day,'level':level,
                       'entry':entry,'stop':stop,'risk':float(risk),'atr5_at_retest':float(a),
                       'regime':str(d.regime.iloc[ei]),'utc_hour':int(d.index[ei].hour),
                       'break_atr15':float(b.atr15_prior)}
                break
        if found is not None: out.append(found); used.add(key)
    return pd.DataFrame(out)

def simulate(d,c,target,start,end):
    ei=int(c['entry_i']); last=ei+MAX_HOLD-1
    if int(c['break_last_i'])<start or ei<start or ei>=end or last>=end or last>=len(d): return None
    side=c['side']; direction=1. if side=='long' else -1.
    entry=float(c['entry']); stop=float(c['stop']); risk=float(c['risk']); tgt=entry+direction*target*risk
    seg=int(d.seg.iloc[ei]); xp=None; xi=None; reason=None
    for j in range(ei,last+1):
        if int(d.seg.iloc[j])!=seg:
            return {'unresolved':True,'entry_i':ei,'entry_time':c['entry_time'],'reason':'gap_before_first_exit'}
        o,hi,lo,cl=map(float,(d.open.iloc[j],d.high.iloc[j],d.low.iloc[j],d.close.iloc[j]))
        if side=='long':
            if o<=stop: xp,reason=o,'SL_GAP'
            elif o>=tgt: xp,reason=tgt,'TP_GAP'
            else:
                sh,th=lo<=stop,hi>=tgt
                if sh and th: xp,reason=stop,'SL_AMBIGUOUS_STOP_FIRST'
                elif sh: xp,reason=stop,'SL'
                elif th: xp,reason=tgt,'TP'
        else:
            if o>=stop: xp,reason=o,'SL_GAP'
            elif o<=tgt: xp,reason=tgt,'TP_GAP'
            else:
                sh,th=hi>=stop,lo<=tgt
                if sh and th: xp,reason=stop,'SL_AMBIGUOUS_STOP_FIRST'
                elif sh: xp,reason=stop,'SL'
                elif th: xp,reason=tgt,'TP'
        if reason: xi=j; break
        if j==last: xp,xi,reason=cl,j,'TIME'
    if xp is None: return {'unresolved':True,'entry_i':ei,'entry_time':c['entry_time'],'reason':'no_exit'}
    return {**c,'target_r':target,'target_price':tgt,'exit_i':xi,'exit_time':d.index[xi],
            'exit_price':float(xp),'exit_reason':reason,'gross_r':float(direction*(xp-entry)/risk),
            'holding_bars':int(xi-ei+1),'unresolved':False}

def execute(d,cands,target,start,end,sample):
    out=[]; unresolved=0; last_exit=start-1
    if cands.empty: return pd.DataFrame(),unresolved
    for c in cands.sort_values('entry_i').to_dict('records'):
        r=simulate(d,c,target,start,end)
        if r is None: continue
        if r.get('unresolved'):
            unresolved+=1; last_exit=max(last_exit,int(r['entry_i'])+MAX_HOLD-1); continue
        if int(r['entry_i'])<=last_exit: continue
        r['sample']=sample; out.append(r); last_exit=int(r['exit_i'])
    return pd.DataFrame(out),unresolved

def maxdd(v):
    if not len(v): return 0.
    eq=np.cumsum(v); peak=np.maximum.accumulate(np.r_[0.,eq])[1:]
    return float(np.min(eq-peak))

def metrics(t,cost):
    if t.empty: return {'trades':0,'longs':0,'shorts':0,'win_rate_pct':None,'pf':None,'gross_r':0.,'net_r':0.,'avg_net_r':None,'max_drawdown_r':0.,'max_losing_streak':0,'positive_months':0,'active_months':0,'positive_month_fraction':None}
    x=t.copy(); x['cost_r']=cost/10000*x.entry/x.risk; x['net_r']=x.gross_r-x.cost_r
    v=x.net_r.to_numpy(float); w=v[v>0]; l=v[v<0]
    pf=float(w.sum()/abs(l.sum())) if len(l) else (float('inf') if len(w) else 0.)
    streak=mx=0
    for z in v: streak=streak+1 if z<0 else 0; mx=max(mx,streak)
    month=pd.to_datetime(x.entry_time,utc=True).dt.to_period('M').astype(str)
    m=x.assign(month=month).groupby('month').net_r.sum()
    return {'trades':len(x),'longs':int((x.side=='long').sum()),'shorts':int((x.side=='short').sum()),
            'win_rate_pct':float((v>0).mean()*100),'pf':pf,'gross_r':float(x.gross_r.sum()),'net_r':float(v.sum()),
            'avg_net_r':float(v.mean()),'max_drawdown_r':maxdd(v),'max_losing_streak':mx,
            'positive_months':int((m>0).sum()),'active_months':len(m),'positive_month_fraction':float((m>0).mean())}

def run(out):
    out.mkdir(parents=True,exist_ok=True); raw,dm=fetch(); raw.to_csv(out/'btc_5m_source.csv')
    d,m15,fm=features(raw); c=candidates(d,m15); c.to_csv(out/'pdrt_candidates.csv',index=False)
    n=len(d); a=int(n*.70); b=int(n*.85); bounds={'development':(0,a),'validation':(a,b),'untouched_oos':(b,n)}
    rows=[]; monthly=[]; regimes=[]; gates={}; unresolved={}
    for target in TARGETS:
        unresolved[target]={}
        for sample in ('development','validation'):
            s,e=bounds[sample]; t,u=execute(d,c,target,s,e,sample); unresolved[target][sample]=u
            if not t.empty: t.to_csv(out/f"pdrt_trades_{str(target).replace('.','p')}_{sample}.csv",index=False)
            for cost in COSTS: rows.append({'target_r':target,'sample':sample,'cost_bps_round_trip':cost,'unresolved_paths':u,**metrics(t,cost)})
            if not t.empty:
                x=t.copy(); x['net_r_12bp']=x.gross_r-(12/10000*x.entry/x.risk)
                x['month']=pd.to_datetime(x.entry_time,utc=True).dt.to_period('M').astype(str)
                for m,g in x.groupby('month'): monthly.append({'target_r':target,'sample':sample,'month':m,'trades':len(g),'net_r_12bp':float(g.net_r_12bp.sum()),'positive':bool(g.net_r_12bp.sum()>0)})
                for reg,g in t.groupby('regime'): regimes.append({'target_r':target,'sample':sample,'regime':reg,**metrics(g,12)})
        dev=next(r for r in rows if r['target_r']==target and r['sample']=='development' and r['cost_bps_round_trip']==12)
        val=next(r for r in rows if r['target_r']==target and r['sample']=='validation' and r['cost_bps_round_trip']==12)
        passed=bool(dev['trades']>=100 and val['trades']>=30 and dev['net_r']>0 and val['net_r']>0 and dev['pf']>1 and val['pf']>1 and dev['avg_net_r']>0 and val['avg_net_r']>0 and (dev['positive_month_fraction'] or 0)>=.5 and (val['positive_month_fraction'] or 0)>=.5)
        gates[str(target)]={'passes_development_and_validation':passed,'development':dev,'validation':val}
    pd.DataFrame(rows).to_csv(out/'pdrt_summary.csv',index=False)
    pd.DataFrame(monthly).to_csv(out/'pdrt_monthly.csv',index=False)
    pd.DataFrame(regimes).to_csv(out/'pdrt_regimes.csv',index=False)
    oos=any(x['passes_development_and_validation'] for x in gates.values())
    if oos:
        for target in TARGETS:
            if gates[str(target)]['passes_development_and_validation']:
                t,u=execute(d,c,target,b,n,'untouched_oos'); unresolved[target]['untouched_oos']=u
                if not t.empty: t.to_csv(out/f"pdrt_trades_{str(target).replace('.','p')}_untouched_oos.csv",index=False)
    meta={'strategy':'BTC prior UTC-day range break/retest','branch':'ai-quant-rebuild','dataset':dm,'features':fm,
          'split':{'rows':n,'development_end_index':a,'validation_end_index':b,'fractions':[.70,.15,.15],'oos_evaluated':oos},
          'rules':{'breakout':'completed 15m close >= prior UTC-day high + 0.10 prior 15m ATR14, or <= prior UTC-day low - 0.10 ATR',
                   'retest':'within next 12 5m bars; touch within 0.15 prior 5m ATR; close back on breakout side in directional half',
                   'entry':'next 5m open; cancel if it opens back inside range','stop':'beyond retest extreme by 0.10 prior 5m ATR; skip risk >2.5 ATR',
                   'targets_R':list(TARGETS),'max_holding_hours':4,'same_bar':'stop first','stop_gap':'worse open','target_gap':'target price',
                   'gap_during_trade':'unresolved, excluded; reserve full 4h window before next trade'},
          'costs_bps_round_trip':list(COSTS),'primary_cost_bps':12,'funding':'excluded; settlement mapping not verified',
          'other_costs':'spread, slippage and market impact not separately modelled','candidate_count':len(c),'gate':gates,
          'decision':'OOS not evaluated; no target passed both development and validation' if not oos else 'OOS evaluated only for passing targets',
          'unresolved_paths':unresolved}
    (out/'metadata.json').write_text(json.dumps(meta,indent=2,default=str))
    print(json.dumps({'dataset':dm,'features':fm,'candidate_count':len(c),'summary':rows,'gate':gates,'oos_evaluated':oos},indent=2,default=str))

def self_test():
    idx=pd.date_range('2026-01-01',periods=3*288,freq='5min',tz='UTC'); base=np.arange(len(idx),dtype=float)+1000
    raw=pd.DataFrame({'open':base,'high':base+2,'low':base-2,'close':base+.5,'volume':1.},index=idx)
    d=segments(raw); daily=d[['open','high','low','close','volume','seg']].resample('1D',label='right',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum','seg':'nunique'})
    cnt=d.close.resample('1D',label='right',closed='left').count(); daily=daily.loc[cnt.eq(288)&daily.seg.eq(1)]
    mapped=daily.high.reindex(d.index.floor('D')); assert mapped.iloc[288]==raw.high.iloc[:288].max()
    fd_features,fm15,_=features(raw); assert fd_features.prior_day_high.iloc[288]==raw.high.iloc[:288].max() and len(fm15)==288
    future=d.copy(); future.loc[idx[288]:idx[575],'high']=999999.
    fd=future[['open','high','low','close','volume','seg']].resample('1D',label='right',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum','seg':'nunique'})
    fc=future.close.resample('1D',label='right',closed='left').count(); fd=fd.loc[fc.eq(288)&fd.seg.eq(1)]
    assert fd.high.reindex(future.index.floor('D')).iloc[288]==mapped.iloc[288]
    ti=pd.date_range('2026-01-02',periods=60,freq='5min',tz='UTC')
    td=pd.DataFrame({'open':111.,'high':112.,'low':110.,'close':111.5,'volume':1.,'seg':1,'atr5_prior':1.,'regime':'bull'},index=ti)
    mt=pd.DataFrame({'open':[109.],'high':[112.],'low':[108.],'close':[111.],'volume':[3.],'seg':[1],'atr15_prior':[1.],'prior_day_high':[110.],'prior_day_low':[90.]},index=pd.DatetimeIndex([ti[3]],name='timestamp'))
    cs=candidates(td,mt); assert len(cs)==1 and cs.iloc[0].side=='long' and cs.iloc[0].entry_i==4
    c={'entry_i':0,'break_last_i':0,'entry_time':idx[0],'side':'long','day':'2026-01-01','level':100.,'entry':100.,'stop':99.,'risk':1.,'regime':'neutral','retest_time':idx[0],'retest_i':0}
    toy=pd.DataFrame({'open':[100.]*48,'high':[103.]+[100.]*47,'low':[98.]+[100.]*47,'close':[100.]*48,'seg':[1]*48},index=idx[:48])
    z=simulate(toy,c,2.,0,48); assert z and z['exit_reason']=='SL_AMBIGUOUS_STOP_FIRST' and z['gross_r']==-1.
    gap=toy.copy(); gap['high']=100.5; gap['low']=99.5; gap.loc[gap.index[10]:,'seg']=2
    z=simulate(gap,c,2.,0,48); assert z and z.get('unresolved') is True
    assert TARGETS==(1.5,2.,3.)
    print('PDRT synthetic tests passed: prior-day mapping/no-lookahead, retest entry, stop-first ambiguity, unresolved gaps, frozen target matrix')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--self-test',action='store_true'); p.add_argument('--output-dir',type=Path,default=Path('results/btc-pdrt')); a=p.parse_args()
    self_test() if a.self_test else run(a.output_dir)
