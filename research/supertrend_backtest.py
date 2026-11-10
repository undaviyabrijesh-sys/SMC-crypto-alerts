"""BTCUSD 15m Supertrend research. Causal signal, next-open entry, fixed Supertrend stop, 2R target."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from crt_backtest import fetch

OUT=Path("supertrend_results"); OUT.mkdir(exist_ok=True)
ATR_LEN=7
ATR_MULT=2.5
EMA_LEN=50
COST_RATE=0.0012
MAX_HOLD=pd.Timedelta("7D")
TARGET_R=2.0

def rma(series, length):
    """TradingView-style Wilder RMA, seeded with the first length-value SMA."""
    a=series.to_numpy(dtype=float)
    out=np.full(len(a),np.nan)
    valid=np.flatnonzero(np.isfinite(a))
    if len(valid)<length: return pd.Series(out,index=series.index)
    first=valid[0]
    seed_end=first+length
    if seed_end>len(a) or not np.isfinite(a[first:seed_end]).all():
        return pd.Series(out,index=series.index)
    out[seed_end-1]=float(np.mean(a[first:seed_end]))
    for i in range(seed_end,len(a)):
        if np.isfinite(a[i]):
            out[i]=(out[i-1]*(length-1)+a[i])/length
    return pd.Series(out,index=series.index)

def build_indicators(x, source_mode):
    d=x.copy()
    prev_close=d.close.shift(1)
    tr=pd.concat([(d.high-d.low),(d.high-prev_close).abs(),(d.low-prev_close).abs()],axis=1).max(axis=1)
    atr=rma(tr,ATR_LEN)
    ema50=d.close.ewm(span=EMA_LEN,adjust=False,min_periods=1).mean()
    src=((d.high+d.low)/2.0) if source_mode=="hl2" else ema50
    basic_upper=src+ATR_MULT*atr
    basic_lower=src-ATR_MULT*atr
    upper=np.full(len(d),np.nan); lower=np.full(len(d),np.nan)
    direction=np.ones(len(d),dtype=int); st=np.full(len(d),np.nan)
    bu=basic_upper.to_numpy(); bl=basic_lower.to_numpy(); close=d.close.to_numpy()
    for i in range(len(d)):
        if not np.isfinite(atr.iloc[i]):
            continue
        if i==0 or not np.isfinite(upper[i-1]):
            upper[i]=bu[i]; lower[i]=bl[i]; direction[i]=1; st[i]=upper[i]
            continue
        lower[i]=bl[i] if (bl[i]>lower[i-1] or close[i-1]<lower[i-1]) else lower[i-1]
        upper[i]=bu[i] if (bu[i]<upper[i-1] or close[i-1]>upper[i-1]) else upper[i-1]
        if direction[i-1]==1:
            direction[i]=-1 if close[i]>upper[i] else 1
        else:
            direction[i]=1 if close[i]<lower[i] else -1
        st[i]=lower[i] if direction[i]==-1 else upper[i]
    d["atr"]=atr; d["ema50_15m"]=ema50; d["st_direction"]=direction; d["supertrend"]=st
    # Completed 1H EMA50 is only exposed from its close timestamp onward.
    h=d.resample("1h",label="right",closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last"}).dropna()
    counts=d.close.resample("1h",label="right",closed="left").count()
    h=h.loc[counts.reindex(h.index).eq(4)]
    h_ema=h.close.ewm(span=EMA_LEN,adjust=False,min_periods=1).mean()
    d["ema50_1h"]=h_ema.reindex(d.index,method="ffill")
    return d

def run_segment(d, source_mode, filter_mode, sample, split_time):
    rows=[]; i=0; n=len(d)
    # Do not open trades too close to a segment boundary to allow the full 7-day horizon.
    segment_end=d.index[-1]+pd.Timedelta("15min")
    while i<n-1:
        b=d.iloc[i]
        prev=d.iloc[i-1] if i>0 else None
        if prev is None or not np.isfinite(b.supertrend) or not np.isfinite(prev.supertrend):
            i+=1; continue
        long_flip=(prev.st_direction==1 and b.st_direction==-1)
        short_flip=(prev.st_direction==-1 and b.st_direction==1)
        if not (long_flip or short_flip):
            i+=1; continue
        side="long" if long_flip else "short"
        if filter_mode=="1h_ema50":
            ema=b.ema50_1h
            if not np.isfinite(ema) or (side=="long" and b.close<=ema) or (side=="short" and b.close>=ema):
                i+=1; continue
        signal_time=d.index[i]
        entry_i=i+1; et=d.index[entry_i]
        if et+MAX_HOLD>segment_end:
            i+=1; continue
        entry=float(d.iloc[entry_i].open)
        stop=float(b.supertrend)
        risk=(entry-stop) if side=="long" else (stop-entry)
        if not np.isfinite(risk) or risk<=0 or risk/entry>0.05:
            i+=1; continue
        target=entry+(TARGET_R*risk if side=="long" else -TARGET_R*risk)
        future=d.iloc[entry_i:]
        future=future.loc[future.index<et+MAX_HOLD]
        if future.empty:
            i+=1; continue
        outcome="TIME"; exitp=float(future.iloc[-1].close); exitt=future.index[-1]
        exit_i=entry_i
        for j,(t,q) in enumerate(future.iterrows()):
            sl=(q.low<=stop) if side=="long" else (q.high>=stop)
            tp=(q.high>=target) if side=="long" else (q.low<=target)
            if sl:
                outcome="SL"
                # Adverse gap-through fill; never improve a stop fill.
                op=float(q.open)
                exitp=min(stop,op) if side=="long" else max(stop,op)
                exitt=t; exit_i=entry_i+j; break
            if tp:
                outcome="TP"; exitp=target; exitt=t; exit_i=entry_i+j; break
        gross=(exitp-entry)/risk if side=="long" else (entry-exitp)/risk
        cost=COST_RATE*entry/risk
        rows.append(dict(sample=sample,source=source_mode,filter=filter_mode,side=side,
            signal_time=signal_time,entry_time=et,exit_time=exitt,entry=entry,stop=stop,
            target=target,exit=exitp,outcome=outcome,gross_R=gross,cost_R=cost,net_R=gross-cost))
        # One position at a time. Resume after the exit candle.
        i=max(exit_i+1,entry_i+1)
    return rows

def summarize(d, keys):
    out=[]
    for k,g in d.groupby(keys,sort=False):
        g=g.sort_values("entry_time"); r=g.net_R; pos=r[r>0]; neg=r[r<0]
        dd=r.cumsum()-r.cumsum().cummax(); streak=best=0
        for v in r:
            streak=streak+1 if v<0 else 0; best=max(best,streak)
        vals=k if isinstance(k,tuple) else (k,)
        out.append(dict(zip(keys,vals))|dict(trades=len(g),profitable_pct=round(100*(r>0).mean(),2),
          profit_factor=round(pos.sum()/abs(neg.sum()),3) if len(neg) and neg.sum()!=0 else None,
          net_R=round(r.sum(),2),avg_R=round(r.mean(),3),max_drawdown_R=round(min(0,dd.min()),2),
          max_losing_streak=best,TP=int((g.outcome=="TP").sum()),SL=int((g.outcome=="SL").sum()),
          TIME=int((g.outcome=="TIME").sum())))
    return pd.DataFrame(out)

def main():
    x=fetch("15m").sort_index()
    x.to_csv(OUT/"BTCUSD_15m.csv")
    split=x.index[int(len(x)*0.7)]
    gap=x.index.to_series().diff().dropna()
    all_trades=[]
    for source in ("hl2","ema50"):
        d=build_indicators(x,source)
        for filt in ("none","1h_ema50"):
            for sample,start,end in (
                ("train",x.index[0],split),
                ("test",split,x.index[-1]+pd.Timedelta("15min"))
            ):
                seg=d.loc[(d.index>=start)&(d.index<end)].copy()
                if len(seg)<ATR_LEN+5: continue
                all_trades.extend(run_segment(seg,source,filt,sample,split))
    if not all_trades: raise RuntimeError("No Supertrend trades generated")
    t=pd.DataFrame(all_trades).sort_values("entry_time")
    t.to_csv(OUT/"supertrend_trades.csv",index=False)
    keys=["source","filter","sample"]
    s=summarize(t,keys); s.to_csv(OUT/"supertrend_summary.csv",index=False)
    monthly=t.assign(month=t.entry_time.dt.strftime("%Y-%m"))
    m=summarize(monthly,keys+["month"]); m.to_csv(OUT/"supertrend_monthly.csv",index=False)
    meta={"symbol":"BTCUSD","rows_15m":len(x),"start":str(x.index.min()),"end":str(x.index.max()),
      "gaps_15m":int((gap!=pd.Timedelta("15min")).sum()),"oos_split":str(split),
      "atr_length":ATR_LEN,"atr_multiplier":ATR_MULT,"ema_length":EMA_LEN,
      "target_R":TARGET_R,"max_holding":"7D","round_trip_cost_assumption":COST_RATE,
      "configurations":4,"notes":[
        "TradingView-style Supertrend band recurrence with Wilder RMA ATR; source is HL2 or 15m EMA50",
        "Signals use closed 15m candles; entry at next 15m open",
        "Initial stop is the Supertrend line on the signal candle; fixed for the trade",
        "1H EMA50 filter uses only completed 1H candles and must align with trade direction",
        "One position at a time per configuration; no overlap within each configuration",
        "Stop-first if SL and TP touch in the same 15m candle; stop gap-through fills are adverse",
        "2R fixed target; 7-day maximum holding period; signals within 7 days of segment end are skipped",
        "Chronological 70/30 split; indicators are causal and warm-start from prior price history",
        "12bp round-trip cost is an estimate, not user fee-tier verified; no funding or separate spread model",
        "Experimental baseline only; not a validated/live strategy"
      ]}
    (OUT/"supertrend_methodology.json").write_text(json.dumps(meta,indent=2))
    print("SUPERTREND META",json.dumps(meta))
    print("OOS SUMMARY")
    print(s[s["sample"]=="test"].sort_values("net_R",ascending=False).to_string(index=False))
    print("OOS MONTHLY")
    print(m[m["sample"]=="test"].to_string(index=False))
if __name__=="__main__": main()
