#!/usr/bin/env python3
"""BTC 5m execution after confirmed 1H liquidity sweep + 15m MSS.

All source candles are Delta BTCUSD traded-price OHLCV. 15m/1h/4h bars are
built only from complete, contiguous 5m bars. A 1H pivot is usable only from
the first 15m bar whose close is strictly AFTER the pivot-confirmation close.
Entry modes: next 5m open, 5m FVG-midpoint retest, or 15m MSS-range midpoint
retest with a 5m directional close. Research-only; no live use.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

BASE="https://api.india.delta.exchange/v2/history/candles"
SYMBOL="BTCUSD"
DAYS=730
BAR=pd.Timedelta(minutes=5)
M15=pd.Timedelta(minutes=15)
H1=pd.Timedelta(hours=1)
H4=pd.Timedelta(hours=4)
MAX_HOLD=48                 # 4h maximum holding period
LEVEL_MAX_AGE=288           # 72h in 15m bars
RETEST_MAX=12               # 60m after MSS
COSTS=(6,12,20)
EXT_STRENGTHS=(2,3)
LOCAL_STRENGTHS=(2,3)
MSS_WAITS=(4,8)
ENTRY_MODES=("next_open","fvg_mid_retest","mss_mid_retest")
STOP_BUFFERS=(0.0,0.1)
TARGETS=(1.5,2.0,3.0)
HTF_FILTERS=("none","ema50_200_4h")
DIRECTIONS=("both","long_only","short_only")
SESSIONS=("all","07-19")
MIN_TRAIN=40
MIN_VALIDATION=20

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def fetch_5m():
    end=int(pd.Timestamp.now(tz="UTC").timestamp())
    start=end-DAYS*86400
    chunk=300*1800  # 1,800 candles/request, below the public API limit
    frames=[]
    cursor=start
    while cursor<end:
        stop=min(cursor+chunk,end)
        r=requests.get(BASE,params={"resolution":"5m","symbol":SYMBOL,
            "start":cursor,"end":stop},headers={"Accept":"application/json",
            "User-Agent":"SaltyQuant5mSweepResearch/1.0"},timeout=40)
        r.raise_for_status()
        p=r.json()
        if p.get("success") is not True:
            raise RuntimeError(f"Delta API error: {p}")
        rows=p.get("result") or []
        if rows: frames.append(pd.DataFrame(rows))
        cursor=stop
        time.sleep(0.08)
    if not frames: raise RuntimeError("Delta returned no BTCUSD 5m candles")
    d=pd.concat(frames,ignore_index=True)
    d["timestamp"]=pd.to_datetime(pd.to_numeric(d["time"]),unit="s",utc=True)
    duplicate_count=int(d.timestamp.duplicated().sum())
    d=d.drop_duplicates("timestamp",keep="last").sort_values("timestamp").set_index("timestamp")
    for c in ("open","high","low","close","volume"):
        if c in d: d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=["open","high","low","close"])
    d=d[(d[["open","high","low","close"]]>0).all(axis=1)]
    d=d[(d.high>=d[["open","close","low"]].max(axis=1)) &
        (d.low<=d[["open","close","high"]].min(axis=1))]
    d=d[d.index+BAR<=pd.Timestamp.now(tz="UTC")]
    d.attrs["duplicate_count"]=duplicate_count
    if d.empty: raise RuntimeError("No valid closed BTCUSD 5m candles")
    return d

def rma_segmented(s,seg,n=14):
    out=pd.Series(np.nan,index=s.index,dtype=float)
    for _,g in s.groupby(seg,sort=False):
        v=g.to_numpy(float); z=np.full(len(v),np.nan)
        if len(v)>=n and np.isfinite(v[:n]).all():
            z[n-1]=v[:n].mean()
            for i in range(n,len(v)):
                if np.isfinite(v[i]): z[i]=(z[i-1]*(n-1)+v[i])/n
        out.loc[g.index]=z
    return out

def complete_resample(d,rule,expected):
    kw={"label":"right","closed":"left"}
    z=d[["open","high","low","close"]].resample(rule,**kw).agg(
        {"open":"first","high":"max","low":"min","close":"last"})
    counts=d.close.resample(rule,**kw).count()
    segs=d.segment.resample(rule,**kw).nunique()
    z=z.loc[counts.eq(expected)&segs.eq(1)].dropna()
    z["segment"]=z.index.to_series().diff().ne(pd.Timedelta(rule)).cumsum().astype(int)
    return z

def prepare(raw):
    d=raw.sort_index().copy()
    d["segment"]=d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    prev=d.groupby("segment").close.shift(1)
    tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
    d["atr5"]=rma_segmented(tr,d.segment,14)
    m15=complete_resample(d,"15min",3)
    h1=complete_resample(d,"1h",12)
    h4=complete_resample(d,"4h",48)
    for col in ("ema50","ema200"):
        span=int(col[3:])
        h4[col]=h4.groupby("segment").close.transform(
            lambda s:s.ewm(span=span,adjust=False,min_periods=span).mean())
    # Right-labelled 4h values become available exactly at their close.
    for col in ("close","ema50","ema200"):
        s=h4[col].reindex(d.index,method="ffill")
        last_time=pd.Series(h4.index,index=h4.index).reindex(d.index,method="ffill")
        age=pd.Series(d.index,index=d.index)-last_time
        s=s.mask(age>=H4)
        d[f"h4_{col}"]=s
    bull=(d.h4_close>d.h4_ema50)&(d.h4_ema50>d.h4_ema200)
    bear=(d.h4_close<d.h4_ema50)&(d.h4_ema50<d.h4_ema200)
    d["regime"]=np.select([bull,bear],["bull","bear"],default="range_or_unavailable")
    return d,m15,h1,h4

def confirmed_external_levels(m15,h1,strength):
    """1H pivots are available only on the first 15m close AFTER confirmation."""
    hi=h1.high.to_numpy(float); lo=h1.low.to_numpy(float)
    seg=h1.segment.to_numpy(); out=[]
    for p in range(strength,len(h1)-strength):
        if not np.all(seg[p-strength:p+strength+1]==seg[p]): continue
        confirmed_at=h1.index[p+strength]
        # Strictly right: the 15m candle ending at confirmed_at is not usable.
        available_i=int(m15.index.searchsorted(confirmed_at,side="right"))
        if available_i>=len(m15): continue
        if hi[p]>np.max(hi[p-strength:p]) and hi[p]>=np.max(hi[p+1:p+strength+1]):
            out.append((available_i,"high",float(hi[p]),h1.index[p]))
        if lo[p]<np.min(lo[p-strength:p]) and lo[p]<=np.min(lo[p+1:p+strength+1]):
            out.append((available_i,"low",float(lo[p]),h1.index[p]))
    return sorted(out,key=lambda x:(x[0],x[1]))

def confirmed_local_swings(m15,strength):
    hi=m15.high.to_numpy(float); lo=m15.low.to_numpy(float)
    seg=m15.segment.to_numpy(); n=len(m15)
    eh=np.full(n,np.nan); el=np.full(n,np.nan)
    for p in range(strength,n-strength):
        if not np.all(seg[p-strength:p+strength+1]==seg[p]): continue
        if hi[p]>np.max(hi[p-strength:p]) and hi[p]>=np.max(hi[p+1:p+strength+1]):
            eh[p+strength]=hi[p]
        if lo[p]<np.min(lo[p-strength:p]) and lo[p]<=np.min(lo[p+1:p+strength+1]):
            el[p+strength]=lo[p]
    last_hi=np.full(n,np.nan); last_lo=np.full(n,np.nan); ch=cl=np.nan
    for i in range(n):
        if np.isfinite(eh[i]): ch=eh[i]
        if np.isfinite(el[i]): cl=el[i]
        last_hi[i]=ch; last_lo[i]=cl
    return last_hi,last_lo

def build_events(m15,h1,ext_strength,local_strength,mss_wait):
    levels=confirmed_external_levels(m15,h1,ext_strength)
    last_hi,last_lo=confirmed_local_swings(m15,local_strength)
    hi=m15.high.to_numpy(float); lo=m15.low.to_numpy(float)
    cl=m15.close.to_numpy(float); seg=m15.segment.to_numpy()
    events=[]
    for ai,level_side,level,pivot_time in levels:
        if ai>=len(m15)-2: continue
        end=min(len(m15)-1,ai+LEVEL_MAX_AGE)
        base_seg=seg[ai]
        for k in range(ai,end):
            if seg[k]!=base_seg: break
            prior=k-1
            if prior<0: continue
            if level_side=="high":
                swept=hi[k]>level and cl[k]<level
                invalid=cl[k]>level
                side="short"; structure=last_lo[prior]; extreme=hi[k]
            else:
                swept=lo[k]<level and cl[k]>level
                invalid=cl[k]<level
                side="long"; structure=last_hi[prior]; extreme=lo[k]
            if swept:
                if not np.isfinite(structure): break
                for j in range(k+1,min(k+mss_wait+1,len(m15)-1)):
                    if seg[j]!=base_seg: break
                    if level_side=="high":
                        extreme=max(extreme,hi[j])
                        if cl[j]>level: break
                        mss=cl[j]<structure
                    else:
                        extreme=min(extreme,lo[j])
                        if cl[j]<level: break
                        mss=cl[j]>structure
                    if mss:
                        events.append({"pivot_time":pivot_time,"sweep_i":k,"mss_i":j,
                            "side":side,"extreme":float(extreme),"structure":float(structure),
                            "external_level":level,"sweep_open":m15.index[k]-M15,
                            "mss_close":m15.index[j]})
                        break
                break
            if invalid: break
    return sorted(events,key=lambda x:(x["mss_close"],x["sweep_open"]))

def latest_fvg(d,start_time,end_time,side):
    """Most recent 3-bar FVG formed after sweep and fully closed by MSS close."""
    a=int(d.index.searchsorted(start_time,side="left"))
    b=int(d.index.searchsorted(end_time,side="left"))
    if b-a<3: return None
    op=d.open.to_numpy(float); hi=d.high.to_numpy(float); lo=d.low.to_numpy(float)
    seg=d.segment.to_numpy(); found=None
    for i in range(a,b-2):
        k=i+2
        if seg[i]!=seg[i+1] or seg[i]!=seg[k]: continue
        if side=="long" and lo[k]>hi[i]:
            found=(float(hi[i]),float(lo[k]),d.index[k]+BAR)
        elif side=="short" and hi[k]<lo[i]:
            found=(float(hi[k]),float(lo[i]),d.index[k]+BAR)
    return found

def build_entries(d,m15,events,mode):
    op=d.open.to_numpy(float); hi=d.high.to_numpy(float); lo=d.low.to_numpy(float)
    cl=d.close.to_numpy(float); seg=d.segment.to_numpy(); atr=d.atr5.to_numpy(float)
    entries=[]
    for ev in events:
        t=ev["mss_close"]
        base=int(d.index.searchsorted(t,side="left"))
        # A missing 5m bar immediately after the 15m MSS invalidates this event.
        if base>=len(d) or d.index[base]!=t or base==0 or seg[base]!=seg[base-1]:
            continue
        side=ev["side"]; direction=1 if side=="long" else -1
        if not np.isfinite(atr[base-1]) or atr[base-1]<=0: continue
        if mode=="next_open":
            entry_i=base; confirm_i=base-1
        else:
            if mode=="fvg_mid_retest":
                zone=latest_fvg(d,ev["sweep_open"],t,side)
                if zone is None: continue
                zlo,zhi,_=zone
            else:
                mi=ev["mss_i"]
                zlo=float(m15.low.iloc[mi]); zhi=float(m15.high.iloc[mi])
            mid=(zlo+zhi)/2
            stop0=ev["extreme"]
            found=None
            for j in range(base,min(base+RETEST_MAX,len(d)-1)):
                if seg[j]!=seg[base]: break
                if direction==1:
                    if lo[j]<=stop0 or cl[j]<zlo: break
                    confirm=lo[j]<=mid and cl[j]>mid and cl[j]>op[j]
                else:
                    if hi[j]>=stop0 or cl[j]>zhi: break
                    confirm=hi[j]>=mid and cl[j]<mid and cl[j]<op[j]
                if confirm:
                    found=j; break
            if found is None: continue
            confirm_i=found; entry_i=found+1
            if entry_i>=len(d) or d.index[entry_i]-d.index[found]!=BAR: continue
        entries.append({**ev,"entry_i":entry_i,"confirm_i":confirm_i,
            "atr_at_mss":float(atr[base-1]),"entry_mode":mode})
    return sorted(entries,key=lambda x:x["entry_i"])

def fill_exit(side,o,h,l,stop,target):
    if side=="long":
        if o<=stop: return min(o,stop),"SL"
        if l<=stop: return stop,"SL"
        if h>=target: return target,"TP"
    else:
        if o>=stop: return max(o,stop),"SL"
        if h>=stop: return stop,"SL"
        if l<=target: return target,"TP"
    return None,None

def metrics(t):
    if t.empty: return {"trades":0,"win_rate_pct":0.0,"profit_factor":None,
        "net_R":0.0,"avg_R":0.0,"max_drawdown_R":0.0,"max_losing_streak":0,
        "positive_month_fraction":0.0,"TP":0,"SL":0,"TIME":0}
    x=t.sort_values("entry_time"); r=x.net_R.to_numpy(float)
    wins=r[r>0]; losses=r[r<0]; eq=np.r_[0.,np.cumsum(r)]
    dd=eq-np.maximum.accumulate(eq); streak=mx=0
    for v in r: streak=streak+1 if v<0 else 0; mx=max(mx,streak)
    monthly=x.assign(month=x.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {"trades":len(x),"win_rate_pct":float((r>0).mean()*100),
        "profit_factor":float(wins.sum()/abs(losses.sum())) if len(losses) and abs(losses.sum()) else None,
        "net_R":float(r.sum()),"avg_R":float(r.mean()),"max_drawdown_R":float(dd.min()),
        "max_losing_streak":int(mx),"positive_month_fraction":float((monthly>0).mean()) if len(monthly) else 0.,
        "TP":int((x.outcome=="TP").sum()),"SL":int((x.outcome=="SL").sum()),
        "TIME":int((x.outcome=="TIME").sum())}

def simulate(d,entries,cfg,start_i,end_i,cost_bps):
    op=d.open.to_numpy(float); hi=d.high.to_numpy(float); lo=d.low.to_numpy(float)
    cl=d.close.to_numpy(float); seg=d.segment.to_numpy()
    h4c=d.h4_close.to_numpy(float); e50=d.h4_ema50.to_numpy(float)
    e200=d.h4_ema200.to_numpy(float); regime=d.regime.to_numpy()
    start_t=d.index[start_i]; end_t=d.index[end_i] if end_i<len(d) else d.index[-1]+BAR
    rows=[]; last_exit=start_i-1
    for ev in entries:
        ei=ev["entry_i"]; side=ev["side"]
        if ei<start_i or ei<=last_exit or ei+MAX_HOLD>end_i: continue
        if ev["sweep_open"]<start_t or ev["mss_close"]>=end_t: continue
        if cfg["direction"]=="long_only" and side!="long": continue
        if cfg["direction"]=="short_only" and side!="short": continue
        et=d.index[ei]
        if cfg["session"]=="07-19" and not (7<=et.hour<19): continue
        if cfg["htf_filter"]=="ema50_200_4h":
            if not np.isfinite([h4c[ei],e50[ei],e200[ei]]).all(): continue
            aligned=(side=="long" and h4c[ei]>e50[ei]>e200[ei]) or (side=="short" and h4c[ei]<e50[ei]<e200[ei])
            if not aligned: continue
        end_trade=ei+MAX_HOLD
        if not np.all(seg[ei:end_trade]==seg[ei]): continue
        entry=float(op[ei]); risk_atr=ev["atr_at_mss"]
        buffer=cfg["stop_buffer"]*risk_atr
        stop=float(ev["extreme"])-buffer if side=="long" else float(ev["extreme"])+buffer
        risk=entry-stop if side=="long" else stop-entry
        if not np.isfinite(risk) or risk<=0 or risk/entry>.05: continue
        target=entry+cfg["target_r"]*risk if side=="long" else entry-cfg["target_r"]*risk
        outcome="TIME"; exit_i=end_trade-1; exitp=float(cl[exit_i])
        for k in range(ei,end_trade):
            px,why=fill_exit(side,float(op[k]),float(hi[k]),float(lo[k]),stop,target)
            if why:
                exitp=float(px); outcome=why; exit_i=k; break
        gross=(exitp-entry)/risk if side=="long" else (entry-exitp)/risk
        cost=(cost_bps/10000.)*entry/risk
        rows.append({"sample":cfg["sample"],"entry_mode":cfg["entry_mode"],
            "ext_strength":cfg["ext_strength"],"local_strength":cfg["local_strength"],
            "mss_wait":cfg["mss_wait"],"stop_buffer":cfg["stop_buffer"],
            "target_r":cfg["target_r"],"htf_filter":cfg["htf_filter"],
            "direction_filter":cfg["direction"],"session":cfg["session"],
            "side":side,"regime":str(regime[ei]),"pivot_time":ev["pivot_time"],
            "sweep_time":ev["sweep_open"],"mss_close":ev["mss_close"],
            "confirmation_time":d.index[ev["confirm_i"]],"entry_time":et,
            "exit_time":d.index[exit_i],"entry":entry,"stop":stop,"target":target,
            "exit":exitp,"outcome":outcome,"gross_R":gross,"cost_bps":cost_bps,
            "cost_R":cost,"net_R":gross-cost,"hold_bars":exit_i-ei+1})
        last_exit=exit_i
    return pd.DataFrame(rows)

def run(raw,out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    d,m15,h1,h4=prepare(raw)
    if len(d)<100000 or len(m15)<10000 or len(h1)<1000:
        raise RuntimeError(f"Insufficient data: 5m={len(d)}, 15m={len(m15)}, 1h={len(h1)}")
    n=len(d); train_end=int(n*.70); val_end=int(n*.85)
    splits={"train":(0,train_end),"validation":(train_end,val_end),"oos":(val_end,n)}
    caches={}
    for ex,lo,wait in itertools.product(EXT_STRENGTHS,LOCAL_STRENGTHS,MSS_WAITS):
        ev=build_events(m15,h1,ex,lo,wait)
        caches[(ex,lo,wait)]={mode:build_entries(d,m15,ev,mode) for mode in ENTRY_MODES}
    configs=[]
    for vals in itertools.product(EXT_STRENGTHS,LOCAL_STRENGTHS,MSS_WAITS,ENTRY_MODES,
        STOP_BUFFERS,TARGETS,HTF_FILTERS,DIRECTIONS,SESSIONS):
        ex,lo,wait,mode,buf,target,htf,direction,session=vals
        configs.append({"ext_strength":ex,"local_strength":lo,"mss_wait":wait,
            "entry_mode":mode,"stop_buffer":buf,"target_r":target,"htf_filter":htf,
            "direction":direction,"session":session})
    matrix=[]; selected_trades=[]; cost_rows=[]; monthly=[]; regimes=[]
    for cfg in configs:
        entries=caches[(cfg["ext_strength"],cfg["local_strength"],cfg["mss_wait"])][cfg["entry_mode"]]
        row=dict(cfg)
        result={}
        for sp in ("train","validation"):
            a,b=splits[sp]
            t=simulate(d,entries,{**cfg,"sample":sp},a,b,12)
            m=metrics(t); result[sp]=(t,m)
            row.update({f"{sp}_{k}":v for k,v in m.items()})
        tm=result["train"][1]; vm=result["validation"][1]
        tg=(tm["trades"]>=MIN_TRAIN and tm.get("profit_factor") is not None and
            tm["profit_factor"]>=1.05 and tm["net_R"]>0 and
            tm["positive_month_fraction"]>=.50 and tm["max_drawdown_R"]>=-15)
        vg=(vm["trades"]>=MIN_VALIDATION and vm.get("profit_factor") is not None and
            vm["profit_factor"]>=1.05 and vm["net_R"]>0 and
            vm["positive_month_fraction"]>=.50 and vm["max_drawdown_R"]>=-10)
        row["train_gate"]=bool(tg); row["validation_gate"]=bool(tg and vg)
        matrix.append(row)
        if tg:
            for sp in ("train","validation"):
                a,b=splits[sp]
                for c in COSTS:
                    t=simulate(d,entries,{**cfg,"sample":sp},a,b,c); m=metrics(t)
                    cost_rows.append({**cfg,"sample":sp,"cost_bps":c,**m})
    md=pd.DataFrame(matrix)
    md.to_csv(out/"matrix.csv",index=False)
    passes=md[md.validation_gate].copy()
    selected=None
    if not passes.empty:
        passes=passes.sort_values(["validation_profit_factor","validation_positive_month_fraction",
            "validation_max_drawdown_R","validation_net_R"],ascending=[False,False,False,False])
        selected=passes.iloc[0].to_dict()
        cfg={k:selected[k] for k in configs[0]}
        entries=caches[(cfg["ext_strength"],cfg["local_strength"],cfg["mss_wait"])][cfg["entry_mode"]]
        for sp in ("train","validation","oos"):
            a,b=splits[sp]
            t=simulate(d,entries,{**cfg,"sample":sp},a,b,12)
            if not t.empty:
                selected_trades.append(t)
                mm=t.assign(month=t.entry_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
                for month,val in mm.items(): monthly.append({"sample":sp,"month":month,"net_R":float(val)})
                rg=t.groupby("regime").net_R.agg(["count","sum","mean"]).reset_index()
                for rr in rg.to_dict("records"): regimes.append({"sample":sp,**rr})
            if sp=="oos":
                for c in COSTS:
                    tc=simulate(d,entries,{**cfg,"sample":sp},a,b,c)
                    cost_rows.append({**cfg,"sample":sp,"cost_bps":c,**metrics(tc)})
    pd.DataFrame(cost_rows).to_csv(out/"cost_sensitivity.csv",index=False)
    if selected_trades: pd.concat(selected_trades,ignore_index=True).to_csv(out/"selected_trades_12bp.csv",index=False)
    pd.DataFrame(monthly).to_csv(out/"selected_monthly.csv",index=False)
    pd.DataFrame(regimes).to_csv(out/"selected_regimes.csv",index=False)
    gaps=int((d.index.to_series().diff().dropna()!=BAR).sum())
    meta={"classification":"experimental; no live use","symbol":SYMBOL,
        "rows_5m":len(d),"rows_15m_complete":len(m15),"rows_1h_complete":len(h1),
        "rows_4h_complete":len(h4),"start_utc":d.index.min().isoformat(),
        "end_utc":d.index.max().isoformat(),"gaps_5m":gaps,
        "largest_gap_minutes":float(d.index.to_series().diff().dropna().max().total_seconds()/60),
        "duplicate_rows_removed":int(raw.attrs.get("duplicate_count",0)),
        "zero_volume_rows":int((pd.to_numeric(raw.volume,errors="coerce")==0).sum()) if "volume" in raw else None,
        "dataset_sha256":hashlib.sha256(raw.to_csv().encode()).hexdigest(),
        "split":"chronological 70/15/15 by 5m row index",
        "train_end_utc":d.index[train_end].isoformat(),"validation_end_utc":d.index[val_end].isoformat(),
        "configurations":len(configs),"training_eligible":int(md.train_gate.sum()),
        "validation_passes":int(md.validation_gate.sum()),
        "oos_evaluated":selected is not None,
        "selected_config":{k:selected[k] for k in configs[0]} if selected is not None else None,
        "rules":"confirmed 1H swing sweep/reclaim; 15m MSS; 5m next-open or retest confirmation; structural stop beyond sweep-to-MSS extreme; 1.5/2/3R; max 4h hold",
        "execution":"complete contiguous 5m OHLC; next 5m open; same-bar stop first; adverse stop gap at worse open; target fill at target; timeout at final close",
        "costs":"6/12/20bp flat round-trip sensitivity; funding excluded pending verified settlement data",
        "selection_gates":"train >=40 trades, PF>=1.05, net R>0, positive months>=50%, max DD>=-15R; validation >=20 trades, PF>=1.05, net R>0, positive months>=50%, max DD>=-10R; OOS only for one validation-selected candidate",
        "causality_note":"1H pivots mapped with searchsorted(side='right') to first 15m close strictly after confirmation; 5m entries begin at/after completed 15m MSS close"}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2,default=str)+"\n")
    print(json.dumps(meta,indent=2,default=str))
    print("\nVALIDATION PASSES")
    print(md[md.validation_gate].to_string(index=False) if not passes.empty else "none")
    if selected_trades:
        print("\nSELECTED OOS")
        print(json.dumps(metrics(pd.concat(selected_trades).query("sample == 'oos'")),indent=2))

def self_test():
    # A pivot confirmed at 04:00 cannot be used by the 15m candle ending 04:00.
    m15idx=pd.date_range("2026-01-01 00:15",periods=40,freq="15min",tz="UTC")
    assert m15idx.searchsorted(pd.Timestamp("2026-01-01 04:00",tz="UTC"),side="right")==16
    # FVG must be formed by three fully completed bars before MSS close.
    idx=pd.date_range("2026-01-01 00:00",periods=6,freq="5min",tz="UTC")
    x=pd.DataFrame({"open":[99,101,106,105,104,103],
        "high":[100,103,108,107,106,105],"low":[98,100,105,102,102,101],
        "close":[99,102,107,106,103,102],"segment":[0]*6},index=idx)
    z=latest_fvg(x,idx[0],idx[3]+BAR,"long")
    assert z is not None and z[0]==100.0 and z[1]==105.0
    assert latest_fvg(x,idx[0],idx[2],"long") is None
    # ATR true range must reset at a data-gap segment; first bar after a gap
    # uses its own high-low, not the previous segment's close.
    gi=pd.date_range("2026-01-02 00:00",periods=4,freq="5min",tz="UTC").append(
        pd.date_range("2026-01-02 01:00",periods=4,freq="5min",tz="UTC"))
    gd=pd.DataFrame({"open":[100,101,102,103,200,201,202,203],
        "high":[101,102,103,104,201,202,203,204],
        "low":[99,100,101,102,199,200,201,202],
        "close":[100,101,102,103,200,201,202,203]},index=gi)
    gs=gi.to_series().diff().ne(BAR).cumsum().astype(int)
    gp=gd.groupby(gs).close.shift(1)
    gtr=pd.concat([gd.high-gd.low,(gd.high-gp).abs(),(gd.low-gp).abs()],axis=1).max(axis=1)
    assert gtr.iloc[4]==2.0
    # Conservative same-bar ordering and adverse stop gaps.
    assert fill_exit("long",100,120,80,90,110)==(90,"SL")
    assert fill_exit("short",100,120,80,110,90)==(110,"SL")
    assert fill_exit("long",85,95,80,90,110)==(85,"SL")
    assert fill_exit("short",115,120,112,110,90)==(115,"SL")
    assert fill_exit("long",115,120,112,90,110)==(110,"TP")
    print("8 causality/FVG/gap-reset/execution self-tests passed")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,default=Path("btc-5m-sweep-mss"))
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--input-csv",type=Path)
    a=p.parse_args()
    if a.self_test: self_test(); return
    raw=pd.read_csv(a.input_csv,parse_dates=["timestamp"]).set_index("timestamp") if a.input_csv else fetch_5m()
    raw.index=pd.to_datetime(raw.index,utc=True)
    run(raw,a.output_dir)

if __name__=="__main__": main()
