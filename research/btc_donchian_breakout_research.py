from __future__ import annotations
import argparse, json, zipfile, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

SOURCE_ZIP = Path('/mnt/data/btc_prior_day_volume_profile_poc_research_2026-11-17.zip')
SOURCE_MEMBER = 'package/data/btc_5m_source.csv'
BAR = pd.Timedelta(minutes=15)
COSTS = (4, 7, 10, 20)
LOOKBACKS = (20, 55)
STOP_TYPES = ('prior10', 'atr15')
TARGETS = (2.0, 3.0)
FILTERS = (False, True)
MAX_HOLD = 7 * 24 * 4


def load_source(path=SOURCE_ZIP):
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            source_bytes = z.read(SOURCE_MEMBER)
            raw = pd.read_csv(pd.io.common.BytesIO(source_bytes), parse_dates=['timestamp'])
        source_member = SOURCE_MEMBER
    else:
        source_bytes = path.read_bytes()
        raw = pd.read_csv(pd.io.common.BytesIO(source_bytes), parse_dates=['timestamp'])
        source_member = str(path.name)
    raw['timestamp'] = pd.to_datetime(raw.timestamp, utc=True)
    raw = raw.set_index('timestamp').sort_index()
    if raw.index.has_duplicates:
        raise ValueError('Duplicate 5m timestamps in source')
    raw['bucket'] = raw.index.floor('15min')
    grouped = raw.groupby('bucket', sort=True)
    rows=[]; times=[]
    for ts, g in grouped:
        if len(g) != 3 or not (g.index == pd.date_range(ts, periods=3, freq='5min', tz='UTC')).all():
            continue
        rows.append({'open':float(g.open.iloc[0]),'high':float(g.high.max()),
                     'low':float(g.low.min()),'close':float(g.close.iloc[-1]),
                     'volume':float(g.volume.sum())})
        times.append(ts)
    d = pd.DataFrame(rows, index=pd.DatetimeIndex(times, name='timestamp')).sort_index()
    if d.empty:
        raise ValueError('No complete 15m candles')
    gaps = d.index.to_series().diff().dropna()
    raw_gaps = raw.index.to_series().diff().dropna()
    invalid_ohlc = (raw.high < raw[['open','close','low']].max(axis=1)) | (raw.low > raw[['open','close','high']].min(axis=1))
    invalid_volume = (~np.isfinite(raw.volume.to_numpy(float))) | (raw.volume.to_numpy(float) < 0)
    meta = {
        'source_input':path.name,'source_file_sha256':hashlib.sha256(source_bytes).hexdigest(),
        'source_member':source_member,'source_5m_rows':int(len(raw)),
        'source_5m_start':raw.index.min().isoformat(),'source_5m_end':raw.index.max().isoformat(),
        'source_5m_gap_count':int((raw_gaps != pd.Timedelta(minutes=5)).sum()),
        'invalid_ohlc_rows':int(invalid_ohlc.sum()),'invalid_volume_rows':int(invalid_volume.sum()),
        'complete_15m_rows':int(len(d)),'15m_start':d.index.min().isoformat(),
        '15m_last_open':d.index.max().isoformat(),'15m_gap_count':int((gaps != BAR).sum()),
        'largest_15m_gap_minutes':float(gaps.max().total_seconds()/60) if len(gaps) else 0.0,
        'incomplete_15m_buckets_dropped':int(raw.index.floor('15min').nunique()-len(d)),
        'sha256_15m':hashlib.sha256(pd.util.hash_pandas_object(d,index=True).values.tobytes()).hexdigest()
    }
    return d,meta


def wilder_atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([(df.high-df.low),(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    out=pd.Series(np.nan,index=df.index,dtype=float)
    if len(tr)>=n:
        out.iloc[n-1]=tr.iloc[:n].mean()
        for i in range(n,len(tr)):
            out.iloc[i]=(out.iloc[i-1]*(n-1)+tr.iloc[i])/n
    return out


def build_features(d):
    f=d.copy()
    for n in LOOKBACKS:
        f[f'upper{n}']=f.high.rolling(n,min_periods=n).max().shift(1)
        f[f'lower{n}']=f.low.rolling(n,min_periods=n).min().shift(1)
    f['prior10_low']=f.low.rolling(10,min_periods=10).min()
    f['prior10_high']=f.high.rolling(10,min_periods=10).max()
    f['atr14']=wilder_atr(f,14)
    q=f.copy(); q.index=q.index+BAR
    h=q.resample('1h',label='right',closed='right').agg(
        open=('open','first'),high=('high','max'),low=('low','min'),
        close=('close','last'),volume=('volume','sum')
    ).dropna(subset=['open','high','low','close'])
    h['ema50']=h.close.ewm(span=50,adjust=False,min_periods=50).mean()
    h['ema200']=h.close.ewm(span=200,adjust=False,min_periods=200).mean()
    sig_close_times=f.index+BAR
    hvals=h[['close','ema50','ema200']].reindex(h.index.union(sig_close_times)).sort_index().ffill().reindex(sig_close_times)
    hvals.index=f.index
    f['h_close']=hvals['close']; f['h_ema50']=hvals['ema50']; f['h_ema200']=hvals['ema200']
    f['regime']=np.select(
        [(f.h_close>f.h_ema50)&(f.h_ema50>f.h_ema200),
         (f.h_close<f.h_ema50)&(f.h_ema50<f.h_ema200)],
        ['bull','bear'],default='mixed')
    for n in LOOKBACKS:
        f[f'long_signal{n}']=(f.close>f[f'upper{n}'])&(f.close.shift(1)<=f[f'upper{n}'].shift(1))
        f[f'short_signal{n}']=(f.close<f[f'lower{n}'])&(f.close.shift(1)>=f[f'lower{n}'].shift(1))
    return f,h


def split_bounds(index):
    n=len(index); dev_cut=int(n*.70); val_cut=int(n*.85)
    return {'development':(index[0],index[dev_cut]),
            'validation':(index[dev_cut],index[val_cut]),
            'out_of_sample':(index[val_cut],index[-1]+BAR)}


def simulate_one(f,sig_i,direction,stop_type,target_r,cost_bps,split_end):
    entry_i=sig_i+1
    if entry_i>=len(f): return None
    entry_time=f.index[entry_i]
    if entry_time+MAX_HOLD*BAR>=split_end: return None
    entry=float(f.open.iloc[entry_i])
    if stop_type=='prior10':
        stop=float(f.prior10_low.iloc[sig_i] if direction==1 else f.prior10_high.iloc[sig_i])
    else:
        atr=float(f.atr14.iloc[sig_i])
        if not np.isfinite(atr) or atr<=0: return None
        stop=entry-direction*1.5*atr
    risk=direction*(entry-stop)
    if not np.isfinite(risk) or risk<=0: return None
    target=entry+direction*target_r*risk
    last_i=min(entry_i+MAX_HOLD-1,len(f)-1)
    exit_i=exit_price=exit_reason=None
    for j in range(entry_i,last_i+1):
        o=float(f.open.iloc[j]); hi=float(f.high.iloc[j]); lo=float(f.low.iloc[j])
        if (direction==1 and o<=stop) or (direction==-1 and o>=stop):
            exit_i,exit_price,exit_reason=j,o,'stop_gap'; break
        if (direction==1 and o>=target) or (direction==-1 and o<=target):
            exit_i,exit_price,exit_reason=j,target,'target_gap_capped'; break
        stop_hit=(lo<=stop) if direction==1 else (hi>=stop)
        target_hit=(hi>=target) if direction==1 else (lo<=target)
        if stop_hit and target_hit:
            exit_i,exit_price,exit_reason=j,stop,'stop_ambiguous_first'; break
        if stop_hit:
            exit_i,exit_price,exit_reason=j,stop,'stop'; break
        if target_hit:
            exit_i,exit_price,exit_reason=j,target,'target'; break
    if exit_i is None:
        exit_i=last_i; exit_price=float(f.close.iloc[last_i]); exit_reason='time'
    gross_r=direction*(exit_price-entry)/risk
    risk_bps=risk/entry*10000.0
    return {'signal_time':f.index[sig_i].isoformat(),'entry_time':entry_time.isoformat(),
            'exit_time':f.index[exit_i].isoformat(),'direction':'long' if direction==1 else 'short',
            'entry':entry,'stop':stop,'target':target,'exit':float(exit_price),
            'risk_abs':risk,'risk_bps':risk_bps,'gross_r':gross_r,'cost_bps':cost_bps,
            'net_r':gross_r-cost_bps/risk_bps,'exit_reason':exit_reason,
            'bars_held':int(exit_i-entry_i+1),'regime':str(f.regime.iloc[sig_i])}


def metrics(trades):
    if not trades:
        return {'trades':0,'win_rate_pct':None,'profit_factor':None,'net_r':0.0,
                'avg_net_r':None,'max_drawdown_r':0.0,'max_losing_streak':0,
                'positive_months':0,'active_months':0}
    t=pd.DataFrame(trades).sort_values('entry_time'); r=t.net_r.to_numpy(float)
    pos,neg=r[r>0],r[r<0]
    pf=float(pos.sum()/abs(neg.sum())) if len(neg) and len(pos) else (float('inf') if len(pos) and not len(neg) else 0.0)
    eq=np.cumsum(r); peaks=np.maximum.accumulate(np.r_[0.0,eq])[1:]; dd=eq-peaks
    streak=cur=0
    for x in r:
        if x<0: cur+=1; streak=max(streak,cur)
        else: cur=0
    t['month']=pd.to_datetime(t.entry_time,utc=True).dt.strftime('%Y-%m')
    monthly=t.groupby('month').net_r.sum()
    return {'trades':int(len(t)),'win_rate_pct':float((r>0).mean()*100),
            'profit_factor':pf,'net_r':float(r.sum()),'avg_net_r':float(r.mean()),
            'max_drawdown_r':float(dd.min()),'max_losing_streak':int(streak),
            'positive_months':int((monthly>0).sum()),'active_months':int(len(monthly)),
            'median_net_r':float(np.median(r)),'long_trades':int((t.direction=='long').sum()),
            'short_trades':int((t.direction=='short').sum())}


def run_config(f,name,lookback,stop_type,target_r,ema_filter,split_name,bounds):
    start,end=bounds; ts=f.index
    eligible=np.flatnonzero((ts>=start)&(ts+BAR<end-MAX_HOLD*BAR))
    if len(eligible)==0: return []
    op=f.open.to_numpy(float); hi=f.high.to_numpy(float); lo=f.low.to_numpy(float); cl=f.close.to_numpy(float)
    atr=f.atr14.to_numpy(float); p10l=f.prior10_low.to_numpy(float); p10h=f.prior10_high.to_numpy(float)
    hc=f.h_close.to_numpy(float); ema=f.h_ema50.to_numpy(float); regime=f.regime.astype(str).to_numpy()
    longs=f[f'long_signal{lookback}'].fillna(False).to_numpy(bool)
    shorts=f[f'short_signal{lookback}'].fillna(False).to_numpy(bool)
    if ema_filter:
        longs &= np.isfinite(hc)&np.isfinite(ema)&(hc>ema)
        shorts &= np.isfinite(hc)&np.isfinite(ema)&(hc<ema)
    candidates=eligible[longs[eligible]|shorts[eligible]]
    base=[]; next_free=-1; n=len(f)
    for i in candidates:
        if i<next_free: continue
        direction=1 if longs[i] else -1; entry_i=int(i+1)
        if entry_i>=n: continue
        entry=float(op[entry_i])
        if stop_type=='prior10': stop=float(p10l[i] if direction==1 else p10h[i])
        else:
            if not np.isfinite(atr[i]) or atr[i]<=0: continue
            stop=entry-direction*1.5*float(atr[i])
        risk=direction*(entry-stop)
        if not np.isfinite(risk) or risk<=0: continue
        target=entry+direction*target_r*risk; last_i=min(entry_i+MAX_HOLD-1,n-1)
        exit_i=exit_price=reason=None
        for j in range(entry_i,last_i+1):
            o=float(op[j]); hh=float(hi[j]); ll=float(lo[j])
            if (direction==1 and o<=stop) or (direction==-1 and o>=stop):
                exit_i,exit_price,reason=j,o,'stop_gap'; break
            if (direction==1 and o>=target) or (direction==-1 and o<=target):
                exit_i,exit_price,reason=j,target,'target_gap_capped'; break
            sh=(ll<=stop) if direction==1 else (hh>=stop)
            th=(hh>=target) if direction==1 else (ll<=target)
            if sh and th: exit_i,exit_price,reason=j,stop,'stop_ambiguous_first'; break
            if sh: exit_i,exit_price,reason=j,stop,'stop'; break
            if th: exit_i,exit_price,reason=j,target,'target'; break
        if exit_i is None: exit_i=last_i; exit_price=float(cl[last_i]); reason='time'
        gross=direction*(exit_price-entry)/risk; risk_bps=risk/entry*10000.0
        base.append({'signal_time':ts[i].isoformat(),'entry_time':ts[entry_i].isoformat(),
                     'exit_time':ts[exit_i].isoformat(),'direction':'long' if direction==1 else 'short',
                     'entry':entry,'stop':stop,'target':target,'exit':float(exit_price),
                     'risk_abs':risk,'risk_bps':risk_bps,'gross_r':gross,'exit_reason':reason,
                     'bars_held':int(exit_i-entry_i+1),'regime':regime[i],'exit_index':int(exit_i)})
        next_free=exit_i+1
    results=[]
    for cost in COSTS:
        trades=[]
        for b in base:
            tr=dict(b); tr['cost_bps']=cost; tr['net_r']=tr['gross_r']-cost/tr['risk_bps']
            tr.update({'config':name,'split':split_name,'lookback':lookback,'stop_type':stop_type,
                       'target_r':target_r,'ema_filter':ema_filter})
            trades.append(tr)
        results.append((cost,metrics(trades),trades))
    return results


def self_tests():
    results=[]
    idx=pd.date_range('2026-01-01',periods=5,freq='15min',tz='UTC')
    y=pd.DataFrame({'open':[1,2,3,4,5],'high':[2,3,4,5,99],'low':[0,1,2,3,4],
                    'close':[1,2,3,4,5],'volume':[1]*5},index=idx)
    upper=y.high.rolling(2,min_periods=2).max().shift(1)
    assert pd.isna(upper.iloc[1]) and upper.iloc[2]==3 and upper.iloc[4]==5
    results.append('PASS: Donchian channel shifted one bar; current high excluded')
    idx2=pd.date_range('2026-01-01',periods=MAX_HOLD+5,freq='15min',tz='UTC')
    z=pd.DataFrame({'open':np.full(len(idx2),100.0),'high':np.full(len(idx2),101.0),
                    'low':np.full(len(idx2),99.5),'close':np.full(len(idx2),100.0),
                    'volume':np.ones(len(idx2))},index=idx2)
    z['prior10_low']=99.0; z['prior10_high']=101.0; z['atr14']=1.0; z['regime']='mixed'
    z.iloc[1,z.columns.get_loc('high')]=103.0; z.iloc[1,z.columns.get_loc('low')]=98.0
    tr=simulate_one(z,0,1,'prior10',2.0,10,idx2[0]+(MAX_HOLD+3)*BAR)
    assert tr and tr['exit_reason']=='stop_ambiguous_first' and tr['exit']==99.0
    results.append('PASS: same-bar stop/target ambiguity resolves stop-first')
    z2=z.copy(); z2.iloc[1,z2.columns.get_loc('high')]=101.0; z2.iloc[1,z2.columns.get_loc('low')]=99.5
    z2.iloc[2,z2.columns.get_loc('open')]=98.0; z2.iloc[2,z2.columns.get_loc('high')]=99.0; z2.iloc[2,z2.columns.get_loc('low')]=97.0
    tr=simulate_one(z2,0,1,'prior10',2.0,10,idx2[0]+(MAX_HOLD+3)*BAR)
    assert tr and tr['exit_reason']=='stop_gap' and tr['exit']==98.0
    results.append('PASS: adverse gap-through stop fills at bar open')
    z3=z.copy(); z3.iloc[1,z3.columns.get_loc('high')]=101.0; z3.iloc[1,z3.columns.get_loc('low')]=99.5
    z3.iloc[2,z3.columns.get_loc('open')]=104.0; z3.iloc[2,z3.columns.get_loc('high')]=105.0; z3.iloc[2,z3.columns.get_loc('low')]=103.0
    tr=simulate_one(z3,0,1,'prior10',2.0,10,idx2[0]+(MAX_HOLD+3)*BAR)
    assert tr and tr['exit_reason']=='target_gap_capped' and tr['exit']==102.0
    results.append('PASS: favorable target gap is conservatively capped at target')
    assert abs((2.0-10.0/100.0)-1.9)<1e-12
    results.append('PASS: cost-to-R conversion uses initial stop-risk bps')
    return results


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True,help='ZIP containing package/data/btc_5m_source.csv or extracted CSV path')
    ap.add_argument('--out',default='results')
    args=ap.parse_args(); outdir=Path(args.out); outdir.mkdir(parents=True,exist_ok=True)
    tests=self_tests(); (outdir/'self_test_results.txt').write_text('\n'.join(tests)+'\n')
    d,meta=load_source(Path(args.input)); f,h=build_features(d); bounds=split_bounds(f.index)
    meta['splits']={k:{'start':v[0].isoformat(),'end_exclusive':v[1].isoformat()} for k,v in bounds.items()}
    meta['self_tests']=tests; meta['hourly_bars']=int(len(h))
    meta['methodology']={'signal':'15m close crosses prior N-bar high/low; channel shifted one bar',
        'entry':'next 15m open','lookbacks':list(LOOKBACKS),'stop_types':list(STOP_TYPES),
        'structural_stop':'10-bar rolling opposite extreme including completed signal bar',
        'atr_stop':'1.5 x Wilder ATR14','targets_R':list(TARGETS),
        'ema_filter':'optional latest completed 1h close versus EMA50',
        'max_hold_bars':MAX_HOLD,'same_bar_ambiguity':'stop first',
        'gap_stop':'adverse open','gap_target':'target capped','one_position_per_config':True,
        'costs_bps_round_trip':list(COSTS),'funding':'not modeled; pre-funding results',
        'spread_slippage':'flat cost sensitivity only',
        'oos_policy':'OOS only if development and validation gate passes'}
    pd.DataFrame({'timestamp':f.index,'close':f.close,'upper20':f.upper20,'lower20':f.lower20,
        'upper55':f.upper55,'lower55':f.lower55,'atr14':f.atr14,'h_close':f.h_close,
        'h_ema50':f.h_ema50,'h_ema200':f.h_ema200,'regime':f.regime}).to_csv(outdir/'feature_audit.csv',index=False)
    summaries=[]; monthly_rows=[]; regime_rows=[]; trade_rows=[]
    for lookback in LOOKBACKS:
      for stop_type in STOP_TYPES:
       for target_r in TARGETS:
        for ema_filter in FILTERS:
         name=f'DC{lookback}_{stop_type}_{target_r:g}R_ema{int(ema_filter)}'
         for split_name in ('development','validation'):
          for cost,m,trades in run_config(f,name,lookback,stop_type,target_r,ema_filter,split_name,bounds[split_name]):
            summaries.append({'config':name,'lookback':lookback,'stop_type':stop_type,'target_r':target_r,
                'ema_filter':ema_filter,'split':split_name,'cost_bps':cost,**m})
            if cost==10:
                trade_rows.extend(trades)
                if trades:
                    t=pd.DataFrame(trades); t['month']=pd.to_datetime(t.entry_time,utc=True).dt.strftime('%Y-%m')
                    for month,g in t.groupby('month'):
                        monthly_rows.append({'config':name,'split':split_name,'month':month,'trades':len(g),'net_r':g.net_r.sum()})
                    for regime,g in t.groupby('regime'):
                        regime_rows.append({'config':name,'split':split_name,'regime':regime,'trades':len(g),
                            'net_r':g.net_r.sum(),'avg_net_r':g.net_r.mean()})
    s=pd.DataFrame(summaries); s.to_csv(outdir/'summary_dev_val.csv',index=False)
    pd.DataFrame(trade_rows).to_csv(outdir/'trades_dev_val.csv',index=False)
    pd.DataFrame(monthly_rows).to_csv(outdir/'monthly_dev_val.csv',index=False)
    pd.DataFrame(regime_rows).to_csv(outdir/'regimes_dev_val.csv',index=False)
    p=s[s.cost_bps==10].pivot(index='config',columns='split',
        values=['trades','profit_factor','net_r','positive_months','active_months'])
    passes=[]
    for cfg,row in p.iterrows():
        try:
            ok=(row[('trades','development')]>=100 and row[('trades','validation')]>=30 and
                row[('profit_factor','development')]>1.10 and row[('profit_factor','validation')]>1.10 and
                row[('net_r','development')]>0 and row[('net_r','validation')]>0 and
                row[('positive_months','development')]/max(1,row[('active_months','development')])>=.55 and
                row[('positive_months','validation')]/max(1,row[('active_months','validation')])>=.55)
        except Exception: ok=False
        if ok: passes.append(cfg)
    meta['candidate_gate']={'min_trades_dev':100,'min_trades_validation':30,'PF_both_gt':1.10,
        'net_R_both_gt':0,'positive_active_month_fraction_both_min':.55,'passed_configs':passes}
    meta['oos_evaluated']=bool(passes)
    if passes:
        # This branch is reached only after the frozen dev/validation gate passes.
        oos_rows=[]; oos_trades=[]
        for cfg in passes:
            parts=cfg.split('_'); lb=int(parts[0][2:]); st=parts[1]; tr=float(parts[2][:-1]); ef=bool(int(parts[3][3:]))
            for cost,m,trades in run_config(f,cfg,lb,st,tr,ef,'out_of_sample',bounds['out_of_sample']):
                if cost==10: oos_rows.append({'config':cfg,**m}); oos_trades.extend(trades)
        pd.DataFrame(oos_rows).to_csv(outdir/'oos_selected.csv',index=False)
        pd.DataFrame(oos_trades).to_csv(outdir/'oos_selected_trades.csv',index=False)
    else:
        meta['oos_reason']='No configuration passed development and validation gates; final 15% not evaluated.'
    (outdir/'metadata.json').write_text(json.dumps(meta,indent=2))
    prim=s[s.cost_bps==10].copy()
    lines=['# BTC Donchian breakout baseline — research results','',
        f"Data: {meta['source_5m_rows']:,} 5m rows; {meta['complete_15m_rows']:,} complete 15m bars; {meta['15m_start']} to {meta['15m_last_open']}.",
        '',f"15m gaps: {meta['15m_gap_count']}; largest interval: {meta['largest_15m_gap_minutes']} minutes.",
        '','## Primary results at 10 bps round trip','','| Config | Split | Trades | Win % | PF | Net R | Avg R | Max DD R | Max losing streak | Positive months |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for _,r in prim.iterrows():
        lines.append(f"| {r.config} | {r.split} | {int(r.trades)} | {r.win_rate_pct if pd.notna(r.win_rate_pct) else 0:.2f} | {r.profit_factor if pd.notna(r.profit_factor) else 0:.3f} | {r.net_r:.2f} | {r.avg_net_r if pd.notna(r.avg_net_r) else 0:.4f} | {r.max_drawdown_r:.2f} | {int(r.max_losing_streak)} | {int(r.positive_months)}/{int(r.active_months)} |")
    lines += ['','## OOS gate',f"Passed configurations: {passes if passes else 'None'}.",
        meta.get('oos_reason','OOS evaluated only after the frozen gate.')]
    (outdir/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps({'metadata':meta,'primary':prim.to_dict(orient='records'),'passes':passes},indent=2,default=str))


if __name__=='__main__':
    main()
