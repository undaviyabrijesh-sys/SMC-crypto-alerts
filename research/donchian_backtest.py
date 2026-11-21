"""BTCUSD Donchian breakout research: causal 15m channel break, next-open entry, fixed initial stop."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from crt_backtest import fetch

OUT=Path("donchian_results"); OUT.mkdir(exist_ok=True)
COST_RATE=0.0012
ATR_LEN=14
CHANNELS=(20,55)
STOP_MODES=("prior10","atr1.5")
TARGETS=(2.0,3.0)
FILTERS=("none","1h_ema50")
MAX_HOLD=pd.Timedelta("7D")

def rma(s,n):
    a=s.to_numpy(float); out=np.full(len(a),np.nan)
    if len(a)<n or not np.isfinite(a[:n]).all(): return pd.Series(out,index=s.index)
    out[n-1]=float(np.mean(a[:n]))
    for i in range(n,len(a)):
        if np.isfinite(a[i]): out[i]=(out[i-1]*(n-1)+a[i])/n
    return pd.Series(out,index=s.index)

def indicators(x):
    d=x.copy()
    pc=d.close.shift()
    tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
    d["atr"]=rma(tr,ATR_LEN)
    d["ema20_high"]=d.high.shift(1).rolling(20,min_periods=20).max()
    d["ema20_low"]=d.low.shift(1).rolling(20,min_periods=20).min()
    d["donchian20_high"]=d.high.shift(1).rolling(20,min_periods=20).max()
    d["donchian20_low"]=d.low.shift(1).rolling(20,min_periods=20).min()
    d["donchian55_high"]=d.high.shift(1).rolling(55,min_periods=55).max()
    d["donchian55_low"]=d.low.shift(1).rolling(55,min_periods=55).min()
    d["prior10_low"]=d.low.shift(1).rolling(10,min_periods=10).min()
    d["prior10_high"]=d.high.shift(1).rolling(10,min_periods=10).max()
    # Right-labeled hour bars: the EMA becomes visible only at its completed-hour timestamp.
    h=d.resample("1h",label="right",closed="left").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    counts=d.close.resample("1h",label="right",closed="left").count()
    h=h.loc[counts.reindex(h.index).eq(4)]
    hema=h.close.ewm(span=50,adjust=False,min_periods=1).mean()
    d["ema50_1h"]=hema.reindex(d.index,method="ffill")
    return d

def run(d,channel,stop_mode,target_r,filter_mode,sample):
    rows=[]; i=0; n=len(d)
    if n<channel+2: return rows
    segment_end=d.index[-1]+pd.Timedelta("15min")
    high_col=f"donchian{channel}_high"; low_col=f"donchian{channel}_low"
    while i<n-1:
        b=d.iloc[i]
        if not np.isfinite(b[high_col]) or not np.isfinite(b[low_col]) or not np.isfinite(b.atr):
            i+=1; continue
        long= b.close> b[high_col]
        short= b.close< b[low_col]
        if not (long or short): i+=1; continue
        side="long" if long else "short"
        if filter_mode=="1h_ema50":
            e=b.ema50_1h
            if not np.isfinite(e) or (long and b.close<=e) or (short and b.close>=e):
                i+=1; continue
        signal_time=d.index[i]; entry_i=i+1; et=d.index[entry_i]
        if et+MAX_HOLD>segment_end:
            i+=1; continue
        entry=float(d.iloc[entry_i].open)
        if stop_mode=="prior10":
            stop=float(b.prior10_low if long else b.prior10_high)
        else:
            stop=entry-(1.5*float(b.atr) if long else -1.5*float(b.atr))
        risk=entry-stop if long else stop-entry
        if not np.isfinite(risk) or risk<=0 or risk/entry>0.05:
            i+=1; continue
        target=entry+(target_r*risk if long else -target_r*risk)
        future=d.iloc[entry_i:]
        future=future.loc[future.index<et+MAX_HOLD]
        if future.empty: i+=1; continue
        outcome="TIME"; exitp=float(future.iloc[-1].close); exitt=future.index[-1]
        exit_i=entry_i+len(future)-1
        for j,(t,q) in enumerate(future.iterrows()):
            sl=q.low<=stop if long else q.high>=stop
            tp=q.high>=target if long else q.low<=target
            if sl:
                outcome="SL"; op=float(q.open)
                exitp=min(stop,op) if long else max(stop,op)
                exitt=t; exit_i=entry_i+j; break
            if tp:
                outcome="TP"; exitp=target; exitt=t; exit_i=entry_i+j; break
        gross=(exitp-entry)/risk if long else (entry-exitp)/risk
        cost=COST_RATE*entry/risk
        rows.append(dict(sample=sample,channel=channel,stop_mode=stop_mode,target_R=target_r,
          filter=filter_mode,side=side,signal_time=signal_time,entry_time=et,exit_time=exitt,
          entry=entry,stop=stop,target=target,exit=exitp,outcome=outcome,
          gross_R=gross,cost_R=cost,net_R=gross-cost))
        i=max(exit_i+1,entry_i+1)
    return rows

def summarize(t,keys):
    rows=[]
    for k,g in t.groupby(keys,sort=False):
        g=g.sort_values("entry_time"); r=g.net_R; pos=r[r>0]; neg=r[r<0]
        eq=r.cumsum().to_numpy(); dd=eq-np.maximum.accumulate(np.r_[0.0,eq])[1:]
        streak=best=0
        for v in r: streak=streak+1 if v<0 else 0; best=max(best,streak)
        vals=k if isinstance(k,tuple) else (k,)
        rows.append(dict(zip(keys,vals))|dict(trades=len(g),profitable_pct=round(100*(r>0).mean(),2),
          profit_factor=round(pos.sum()/abs(neg.sum()),3) if len(neg) and neg.sum()!=0 else None,
          net_R=round(r.sum(),2),avg_R=round(r.mean(),3),max_drawdown_R=round(min(0,dd.min()),2),
          max_losing_streak=best,TP=int((g.outcome=="TP").sum()),SL=int((g.outcome=="SL").sum()),
          TIME=int((g.outcome=="TIME").sum())))
    return pd.DataFrame(rows)

def main():
    x=fetch("15m").sort_index(); d=indicators(x)
    split=x.index[int(len(x)*.7)]; gap=x.index.to_series().diff().dropna()
    alltr=[]
    for channel in CHANNELS:
      for stop in STOP_MODES:
       for target in TARGETS:
        for filt in FILTERS:
         for sample,start,end in (("train",x.index[0],split),("test",split,x.index[-1]+pd.Timedelta("15min"))):
          seg=d.loc[(d.index>=start)&(d.index<end)].copy()
          alltr.extend(run(seg,channel,stop,target,filt,sample))
    if not alltr: raise RuntimeError("No Donchian trades generated")
    t=pd.DataFrame(alltr).sort_values("entry_time")
    t.to_csv(OUT/"donchian_trades.csv",index=False)
    keys=["channel","stop_mode","target_R","filter","sample"]
    s=summarize(t,keys); s.to_csv(OUT/"donchian_summary.csv",index=False)
    m=summarize(t.assign(month=t.entry_time.dt.strftime("%Y-%m")),keys+["month"])
    m.to_csv(OUT/"donchian_monthly.csv",index=False)
    meta={"symbol":"BTCUSD","rows_15m":len(x),"start":str(x.index.min()),"end":str(x.index.max()),
      "gaps_15m":int((gap!=pd.Timedelta("15min")).sum()),"oos_split":str(split),
      "channels":CHANNELS,"stops":STOP_MODES,"targets_R":TARGETS,"filters":FILTERS,
      "atr_length":ATR_LEN,"max_holding":"7D","round_trip_cost_assumption":COST_RATE,
      "notes":["Donchian boundaries use prior completed candles only (shifted one bar); signal is close outside channel",
      "Entry at next 15m open; completed 1H EMA50 filter only","One position at a time per configuration",
      "Fixed initial stop: prior 10-bar opposite extreme or 1.5x Wilder ATR(14) from entry",
      "Fixed 2R or 3R target; 7-day max hold; signals without full horizon at each sample boundary are skipped",
      "Stop-first on same 15m candle; adverse gap-through stop fill","12bp round-trip fee estimate; no funding and no separate spread/slippage model",
      "Stop distances above 5% of entry are skipped; chronological 70/30 split",
      "Research baseline only; no parameter optimization or production changes"]}
    (OUT/"donchian_methodology.json").write_text(json.dumps(meta,indent=2))
    print("DONCHIAN META",json.dumps(meta)); print("OOS SUMMARY")
    print(s[s["sample"]=="test"].sort_values("net_R",ascending=False).to_string(index=False))
    print("OOS MONTHLY")
    print(m[m["sample"]=="test"].to_string(index=False))
if __name__=="__main__": main()
