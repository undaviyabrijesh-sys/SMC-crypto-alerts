from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

API='https://api.india.delta.exchange/v2/history/candles'
SYMBOL='BTCUSD'; DAYS=730; BAR=pd.Timedelta(minutes=5)
H={'1h':12,'4h':48}; COSTS=(6,12,20); BOOT=2000; SEED=20261116

def digest(df):
    x=hashlib.sha256()
    for i in range(0,len(df),100000): x.update(df.iloc[i:i+100000].to_csv().encode())
    return x.hexdigest()

def normalize(raw):
    n=len(raw); d=raw.copy()
    if 'timestamp' not in d: d['timestamp']=pd.to_datetime(pd.to_numeric(d.pop('time'),errors='coerce'),unit='s',utc=True)
    else: d['timestamp']=pd.to_datetime(d.timestamp,utc=True,errors='coerce')
    badts=int(d.timestamp.isna().sum()); d=d.dropna(subset=['timestamp'])
    dup=int(d.timestamp.duplicated().sum()); d=d.drop_duplicates('timestamp',keep='last').sort_values('timestamp').set_index('timestamp')
    if 'volume' not in d: d['volume']=0.; missing=len(d)
    else: d['volume']=pd.to_numeric(d.volume,errors='coerce'); missing=int(d.volume.isna().sum()); d['volume']=d.volume.fillna(0.)
    for c in ('open','high','low','close'): d[c]=pd.to_numeric(d[c],errors='coerce')
    a=d[['open','high','low','close']].to_numpy(float); finite=np.isfinite(a).all(1)
    positive=(d[['open','high','low','close']]>0).all(axis=1).to_numpy()
    shape=((d.high>=d[['open','close','low']].max(axis=1))&(d.low<=d[['open','close','high']].min(axis=1))).to_numpy()
    badnf=int((~finite).sum()); badpos=int((finite&~positive).sum()); badshape=int((finite&positive&~shape).sum())
    d=d.loc[finite&positive&shape,['open','high','low','close','volume']]
    d=d[d.index+BAR<=pd.Timestamp.now(tz='UTC')]
    if d.empty: raise RuntimeError('No valid closed BTC 5m candles')
    dif=d.index.to_series().diff().dropna()
    q={'source_rows':n,'valid_rows':len(d),'start_utc':d.index.min().isoformat(),'end_utc':d.index.max().isoformat(),
       'duplicates_removed':dup,'invalid_timestamps':badts,'invalid_nonfinite_ohlc':badnf,'invalid_nonpositive_ohlc':badpos,
       'invalid_ohlc_shape':badshape,'missing_volume':missing,'zero_volume':int((d.volume==0).sum()),
       'gap_count':int((dif!=BAR).sum()),'largest_gap_minutes':float(dif.max().total_seconds()/60) if len(dif) else 0.,'sha256':digest(d)}
    return d,q

def fetch():
    end=int(pd.Timestamp.now(tz='UTC').timestamp()); start=end-DAYS*86400; cur=start; frames=[]; n=0
    while cur<end:
        stop=min(cur+1800*300,end)
        r=requests.get(API,params={'resolution':'5m','symbol':SYMBOL,'start':cur,'end':stop},headers={'Accept':'application/json','User-Agent':'SaltyQuant-EMT/1.0'},timeout=45)
        r.raise_for_status(); p=r.json()
        if p.get('success') is not True: raise RuntimeError(f'Delta API error: {p}')
        rows=p.get('result') or []
        if rows: frames.append(pd.DataFrame(rows)); n+=len(rows)
        cur=stop; time.sleep(.08)
    if not frames: raise RuntimeError('Delta returned no BTC candles')
    d,q=normalize(pd.concat(frames,ignore_index=True)); q['source_rows']=n; return d,q

def segments(d):
    z=d.copy(); z['seg']=z.index.to_series().diff().ne(BAR).cumsum().astype(int); return z

def resample(d,rule,count):
    kw={'label':'right','closed':'left'}
    z=d[['open','high','low','close','volume']].resample(rule,**kw).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    n=d.close.resample(rule,**kw).count(); s=d.seg.resample(rule,**kw).nunique()
    z=z.loc[n.eq(count)&s.eq(1)].dropna(subset=['open','high','low','close'])
    z['seg']=z.index.to_series().diff().ne(pd.Timedelta(rule)).cumsum().astype(int); return z

def tod_quantile(idx,vol,bucket):
    out=pd.Series(np.nan,index=idx,dtype=float); b=pd.Series(bucket,index=idx)
    for _,ix in b.groupby(b).groups.items():
        s=vol.loc[ix]; out.loc[ix]=s.rolling('30D',closed='left',min_periods=20).quantile(.95)
    return out

def features(raw):
    d=segments(raw); prev=d.groupby('seg').close.shift(1)
    d['tr']=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
    d['tr_med20']=d.groupby('seg').tr.transform(lambda s:s.shift(1).rolling(20,min_periods=20).median())
    d['ret12']=d.groupby('seg').close.transform(lambda s:s.shift(1)/s.shift(13)-1)
    h1=resample(d,'1h',12); r1=h1.groupby('seg').close.pct_change().abs()
    q1=r1.rolling('30D',closed='left',min_periods=200).quantile(.90)
    d['ret1h_p90']=q1.reindex(d.index,method='ffill')
    bucket=d.index.hour.to_numpy()*12+d.index.minute.to_numpy()//5
    d['vol_p95']=tod_quantile(d.index,d.volume,bucket)
    h4=resample(d,'4h',48)
    h4['e50']=h4.groupby('seg').close.transform(lambda s:s.ewm(span=50,adjust=False,min_periods=50).mean())
    h4['e200']=h4.groupby('seg').close.transform(lambda s:s.ewm(span=200,adjust=False,min_periods=200).mean())
    bull=(h4.close>h4.e50)&(h4.e50>h4.e200); bear=(h4.close<h4.e50)&(h4.e50<h4.e200)
    h4['regime']=np.select([bull,bear],['bull','bear'],default='neutral')
    d['regime']=h4.regime.reindex(d.index,method='ffill').fillna('neutral')
    rng=(d.high-d.low).replace(0,np.nan); uw=d.high-d[['open','close']].max(axis=1); lw=d[['open','close']].min(axis=1)-d.low
    loc=(d.close-d.low)/rng; d['uw']=uw/rng; d['lw']=lw/rng; d['close_loc']=loc
    up=(d.ret12>d.ret1h_p90)&(d.volume>=d.vol_p95)&(d.tr>=1.5*d.tr_med20)&(d.uw>=.4)&(d.close_loc<=.4)
    dn=(d.ret12< -d.ret1h_p90)&(d.volume>=d.vol_p95)&(d.tr>=1.5*d.tr_med20)&(d.lw>=.4)&(d.close_loc>=.6)
    d['exhaust']=np.select([up,dn],['up','down'],default=''); return d

def events(d):
    o=d.open.to_numpy(float); hi=d.high.to_numpy(float); lo=d.low.to_numpy(float); cl=d.close.to_numpy(float); seg=d.seg.to_numpy(); ex=d.exhaust.to_numpy(str); rows=[]
    for i in np.flatnonzero(ex!=''):
        if i+2>=len(d) or not(seg[i]==seg[i+1]==seg[i+2]): continue
        mid=(hi[i]+lo[i])/2
        if ex[i]=='up': ok=cl[i+1]<o[i+1] and cl[i+1]<mid; side='short'
        else: ok=cl[i+1]>o[i+1] and cl[i+1]>mid; side='long'
        if ok:
            j=i+2; rows.append({'ex_i':i,'confirm_i':i+1,'i':j,'time':d.index[j],'side':side,'regime':str(d.regime.iloc[j]),'date':d.index[j].date().isoformat(),'bucket':int(d.index[j].hour//3),'entry':float(o[j]),'extension':ex[i]})
    if not rows: return pd.DataFrame(columns=['ex_i','confirm_i','i','time','side','regime','date','bucket','entry','extension'])
    e=pd.DataFrame(rows).sort_values('i').reset_index(drop=True); keep=[]; next_time=pd.Timestamp.min.tz_localize('UTC')
    for r in e.itertuples(index=False):
        if r.time>=next_time: keep.append(r.i); next_time=r.time+pd.Timedelta(hours=8)
    return e[e.i.isin(keep)].reset_index(drop=True)

def controls(d,e):
    ret=d.ret12.to_numpy(float); side=np.where(ret>0,'short',np.where(ret<0,'long',''))
    c=pd.DataFrame({'i':np.arange(len(d)),'time':d.index,'side':side,'entry':d.open.to_numpy(float),'regime':d.regime.to_numpy(str),'date':d.index.date.astype(str),'bucket':(d.index.hour//3).astype(int)})
    c=c[c.side!=''].copy()
    if len(e): c=c[~c.i.isin(e.i)]
    return c.reset_index(drop=True)

def bounds(n):
    a=int(n*.70); b=int(n*.85); return {'development':(0,a),'validation':(a,b),'untouched_oos_not_evaluated':(b,n)}

def add_returns(d,c,start,end):
    rows=[]
    for r in c.itertuples(index=False):
        i=int(r.i)
        if i<start or i>=end: continue
        rec={'i':i,'time':pd.Timestamp(r.time),'side':r.side,'entry':float(r.entry),'regime':r.regime,'date':r.date,'bucket':int(r.bucket)}; ok=True
        for h,k in H.items():
            j=i+k-1
            if j>=end or d.seg.iloc[j]!=d.seg.iloc[i]: ok=False; break
            direction=1 if r.side=='long' else -1
            rec[h]=direction*(float(d.close.iloc[j])/float(r.entry)-1)*10000
        if ok: rows.append(rec)
    return pd.DataFrame(rows)

def match(e,c):
    if e.empty or c.empty: return pd.DataFrame()
    groups={k:g.sort_values('time').reset_index(drop=True) for k,g in c.groupby(['date','side','regime','bucket'])}; used=set(); rows=[]
    for _,r in e.sort_values('time').iterrows():
        g=groups.get((r['date'],r['side'],r['regime'],r['bucket']))
        if g is None: continue
        a=g[~g.i.isin(used)]
        if a.empty: continue
        delta=(a.time-r['time']).abs(); m=delta.min(); pick=a.loc[delta.eq(m)].sort_values('time').iloc[0]; used.add(int(pick.i))
        x={'event_i':int(r['i']),'event_time':r['time'].isoformat(),'control_i':int(pick.i),'control_time':pick.time.isoformat(),'side':r['side'],'date':r['date'],'regime':r['regime'],'bucket':int(r['bucket']),'distance_min':float(m.total_seconds()/60)}
        for h in H: x[h+'_event']=float(r[h]); x[h+'_control']=float(pick[h]); x[h+'_lift']=x[h+'_event']-x[h+'_control']
        rows.append(x)
    return pd.DataFrame(rows)

def ci(p,h):
    if p.empty: return (None,None)
    by={k:g[h+'_lift'].to_numpy(float) for k,g in p.groupby('date')}; days=list(by)
    if len(days)<2: return (None,None)
    rng=np.random.default_rng(SEED); vals=np.empty(BOOT)
    for i in range(BOOT): vals[i]=np.mean(np.concatenate([by[x] for x in rng.choice(days,len(days),replace=True)]))
    return tuple(map(float,np.quantile(vals,[.025,.975]))

def metrics(x,dates,cost):
    v=x.to_numpy(float)-cost if len(x) else np.array([])
    if not len(v): return {'events':0,'win_rate_pct':None,'pf':None,'mean_net_bps':None,'median_net_bps':None,'event_sequence_max_dd_bps':None,'max_losing_streak':None,'positive_month_fraction':None,'active_months':0}
    w=v[v>0]; l=v[v<0]; pf=float(w.sum()/abs(l.sum())) if len(l) and abs(l.sum()) else (float('inf') if len(w) else 0.)
    eq=np.cumsum(v); dd=eq-np.maximum.accumulate(np.r_[0.,eq])[1:]; streak=mx=0
    for z in v: streak=streak+1 if z<0 else 0; mx=max(mx,streak)
    months=pd.to_datetime(dates,utc=True).dt.to_period('M').astype(str); m=pd.Series(v).groupby(months.to_numpy()).sum()
    return {'events':len(v),'win_rate_pct':float((v>0).mean()*100),'pf':pf,'mean_net_bps':float(v.mean()),'median_net_bps':float(np.median(v)),'event_sequence_max_dd_bps':float(dd.min()),'max_losing_streak':mx,'positive_month_fraction':float((m>0).mean()),'positive_months':int((m>0).sum()),'active_months':len(m)}

def evaluate(d,ev_all,co_all,span,sample):
    s,e=span; ev=add_returns(d,ev_all,s,e); co=add_returns(d,co_all,s,e)
    sample_event_i=ev_all.loc[(ev_all.i>=s)&(ev_all.i<e),'i'].to_numpy(int) if len(ev_all) else np.array([],dtype=int)
    if len(sample_event_i) and len(co):
        ctimes=pd.DatetimeIndex(co.time); keep=np.ones(len(co),bool)
        for ei in sample_event_i: keep &= np.abs((ctimes-d.index[int(ei)]).total_seconds()/60)>30
        co=co.loc[keep].reset_index(drop=True)
    p=match(ev,co); rows=[]
    for h in H:
        lower,upper=ci(p,h) if len(p) else (None,None)
        for cost in COSTS:
            m=metrics(ev[h] if len(ev) else pd.Series(dtype=float),ev.time if len(ev) else pd.Series(dtype='datetime64[ns, UTC]'),cost)
            rows.append({'sample':sample,'horizon':h,'cost_bps':cost,'matched_pairs':len(p),'matched_event_mean_gross_bps':float(p[h+'_event'].mean()) if len(p) else None,'matched_control_mean_gross_bps':float(p[h+'_control'].mean()) if len(p) else None,'mean_lift_bps':float(p[h+'_lift'].mean()) if len(p) else None,'lift_ci95_low_bps':lower,'lift_ci95_high_bps':upper,**m})
    if len(ev): ev['sample']=sample
    if len(p): p['sample']=sample
    return rows,ev,p

def gate(s):
    out={}
    for h in H:
        a=s[(s.sample=='development')&(s.horizon==h)&(s.cost_bps==12)]; b=s[(s.sample=='validation')&(s.horizon==h)&(s.cost_bps==12)]
        if a.empty or b.empty: out[h]={'passes':False}; continue
        a=a.iloc[0]; b=b.iloc[0]
        def ok(x,ne,npair): return x.events>=ne and x.matched_pairs>=npair and pd.notna(x.mean_net_bps) and x.mean_net_bps>0 and pd.notna(x.mean_lift_bps) and x.mean_lift_bps>0 and pd.notna(x.lift_ci95_low_bps) and x.lift_ci95_low_bps>0 and pd.notna(x.positive_month_fraction) and x.positive_month_fraction>=.5
        da=ok(a,100,50); va=ok(b,30,20)
        out[h]={'development_pass':bool(da),'validation_pass':bool(va),'passes':bool(da and va),'development_events':int(a.events),'development_pairs':int(a.matched_pairs),'validation_events':int(b.events),'validation_pairs':int(b.matched_pairs)}
    return {'any_horizon_passes_both_gates':any(x['passes'] for x in out.values()),'horizons':out,'oos_evaluated':False}

def breakdown(ev,out):
    if ev.empty: return
    ev=ev.copy(); ev['month']=pd.to_datetime(ev.time,utc=True).dt.to_period('M').astype(str)
    monthly=[]; regimes=[]; sides=[]
    for sample,g0 in ev.groupby('sample'):
        for h in H:
            for cost in COSTS:
                g=g0.copy(); g['net']=g[h]-cost
                for month,x in g.groupby('month'): monthly.append({'sample':sample,'horizon':h,'cost_bps':cost,'month':month,'events':len(x),'net_bps_sum':x.net.sum(),'net_bps_mean':x.net.mean()})
                for regime,x in g.groupby('regime'): regimes.append({'sample':sample,'horizon':h,'cost_bps':cost,'regime':regime,'events':len(x),'net_bps_sum':x.net.sum(),'net_bps_mean':x.net.mean()})
                for (side,regime),x in g.groupby(['side','regime']): sides.append({'sample':sample,'horizon':h,'cost_bps':cost,'side':side,'regime':regime,'events':len(x),'net_bps_sum':x.net.sum(),'net_bps_mean':x.net.mean()})
    pd.DataFrame(monthly).to_csv(out/'emt_monthly.csv',index=False); pd.DataFrame(regimes).to_csv(out/'emt_regimes.csv',index=False); pd.DataFrame(sides).to_csv(out/'emt_side_regimes.csv',index=False)

def run(out):
    out.mkdir(parents=True,exist_ok=True); raw,q=fetch()
    if len(raw)<80000: raise RuntimeError(f'Only {len(raw)} 5m bars; need approx two years')
    d=features(raw); ev=events(d); co=controls(d,ev); sp=bounds(len(d)); sm=[]; ers=[]; prs=[]
    for name in ('development','validation'):
        rows,e,p=evaluate(d,ev,co,sp[name],name); sm+=rows
        if len(e): ers.append(e)
        if len(p): prs.append(p)
    summary=pd.DataFrame(sm); er=pd.concat(ers,ignore_index=True) if ers else pd.DataFrame(); pairs=pd.concat(prs,ignore_index=True) if prs else pd.DataFrame()
    summary.to_csv(out/'emt_summary.csv',index=False); er.to_csv(out/'emt_event_returns.csv',index=False); pairs.to_csv(out/'emt_matched_pairs.csv',index=False); ev.to_csv(out/'emt_confirmed_events.csv',index=False); breakdown(er,out)
    g=gate(summary); meta={'classification':'experimental EMT-inspired event study, not a trading strategy','instrument':'Delta Exchange India BTCUSD perpetual traded-price OHLCV','dataset':q,'split':{'method':'chronological 70/15/15 by valid 5m row index','development_end':sp['development'][1],'validation_end':sp['validation'][1],'untouched_oos_range':list(sp['untouched_oos_not_evaluated']),'oos_evaluated':False},'rules':{'extension':'prior 12 completed 5m close-to-close return exceeds prior-only 30D 90th percentile of completed 1h absolute returns; min 200 1h observations','volume':'current volume >= prior-only 30D 95th percentile for same UTC 5m time bucket; min 20 observations','range':'current TR >=1.5x median prior 20 completed 5m TR','rejection':'up extension: upper wick >=40%, close in lower 40%; down extension: lower wick >=40%, close in upper 40%','confirmation':'next completed 5m candle closes in reversal direction beyond exhaustion candle midpoint; enter following 5m open','cooldown':'global one-position event stream and 8h timestamp-based cooldown'},'matching':{'ratio':'1:1 without replacement','keys':['UTC date','direction','completed 4h EMA50/EMA200 regime','3h UTC bucket'],'control_side':'contrarian to prior 12-bar return','exclude_near_event_minutes':30,'tie_break':'earlier control timestamp','bootstrap':'2000 UTC-day cluster replicates, fixed seed 20261116'},'costs_round_trip_bps':list(COSTS),'funding':'excluded; settlement cashflow mapping not verified','spread_slippage':'not separately modelled; flat cost sensitivities only','gate':g,'r_not_applicable':True,'decision':'proceed only to a separate frozen stop/target study if a horizon passes both gates; otherwise reject/rethink; OOS not evaluated'}
    (out/'metadata.json').write_text(json.dumps(meta,indent=2,default=str)+'\n'); print(json.dumps(meta,indent=2,default=str)); print(summary.to_string(index=False))

def self_test():
    ix=pd.date_range('2026-01-01T00:00Z',periods=1000,freq='5min'); base=np.linspace(100,130,len(ix)); d=pd.DataFrame({'open':base,'high':base+.5,'low':base-.5,'close':base+.1,'volume':10.},index=ix); i=500
    d.iloc[i,d.columns.get_loc('open')]=130.; d.iloc[i,d.columns.get_loc('high')]=140.; d.iloc[i,d.columns.get_loc('low')]=128.; d.iloc[i,d.columns.get_loc('close')]=130.5
    d.iloc[i+1,d.columns.get_loc('open')]=130.; d.iloc[i+1,d.columns.get_loc('high')]=131.; d.iloc[i+1,d.columns.get_loc('low')]=120.; d.iloc[i+1,d.columns.get_loc('close')]=121.; d.iloc[i+2,d.columns.get_loc('open')]=120.5
    d=segments(d); d['exhaust']=''; d['regime']='bull'; d['ret12']=.02; d['vol_p95']=5.; d['tr']=2.; d['tr_med20']=1.; d.loc[ix[i],'exhaust']='up'
    e=events(d); assert len(e)==1 and e.iloc[0].i==i+2 and e.iloc[0].side=='short'
    gap=d.drop(ix[i+1]); assert events(segments(gap)).empty
    vi=pd.date_range('2026-01-01',periods=50,freq='1D',tz='UTC'); v=pd.Series(np.arange(50.),index=vi); b=np.zeros(50,int); q1=tod_quantile(vi,v,b); v2=v.copy(); v2.iloc[25:]*=1000; q2=tod_quantile(vi,v2,b); assert q1.iloc[24]==q2.iloc[24]
    e0=pd.DataFrame([{'i':100,'time':pd.Timestamp('2026-01-01T09:00Z'),'side':'short','regime':'bull','date':'2026-01-01','bucket':3,'1h':2.,'4h':3.}]); c0=pd.DataFrame([{'i':98,'time':pd.Timestamp('2026-01-01T08:50Z'),'side':'short','regime':'bull','date':'2026-01-01','bucket':3,'1h':1.,'4h':2.}]); m=match(e0,c0); assert len(m)==1 and m.iloc[0].control_i==98
    p=pd.DataFrame({'date':['2026-01-01','2026-01-02'],'1h_lift':[1.,2.]}); assert ci(p,'1h')==ci(p,'1h')
    ix2=pd.date_range('2026-01-01T00:00Z',periods=5000,freq='5min'); z=np.linspace(100,120,len(ix2)); raw=pd.DataFrame({'open':z,'high':z+.2,'low':z-.2,'close':z+.05,'volume':10.},index=ix2); ff=features(raw); assert 'close_loc' in ff and len(ff)==5000
    print('EMT synthetic tests passed')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',type=Path,default=Path('results/btc-emt-event-study')); ap.add_argument('--self-test',action='store_true'); a=ap.parse_args()
    self_test() if a.self_test else run(a.output_dir)
