"""CRT research v2: causal sweep/reclaim vs MSS, session/OOS comparisons.
Experimental only. Uses 15m Delta BTCUSD bars; all higher timeframes derived from them.
No lookahead, one position at a time per configuration, SL-first ambiguous candles.
"""
import json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from crt_backtest import fetch, OUT

COST_RATE = 0.0012
REFS = {"1h":"1h","4h":"4h","1d":"1D"}
SESSIONS = {"all":None,"london_ny":set(range(7,22))}
def ref_bars(x, rule):
    return x.resample(rule, label="left", closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last"}).dropna()
def test(exe, ref, tf, confirm, target_r, session):
    trades=[]; locked_until=exe.index[0]; delta=pd.Timedelta(tf)
    for rt, rr in ref.iterrows():
        start=rt+delta; end=start+delta
        if start>=exe.index[-1]: break
        if start<=locked_until: continue
        window=exe.loc[(exe.index>=start)&(exe.index<end)]
        if len(window)<3 or (window.index.to_series().diff().dropna()!=pd.Timedelta("15min")).any(): continue
        sweep=None
        for j in range(len(window)-1):
            t=window.index[j]; b=window.iloc[j]
            if session is not None and t.hour not in session: continue
            if b.low<rr.low and rr.low<b.close<rr.high: sweep=(j,"long",b.low,b.high)
            elif b.high>rr.high and rr.low<b.close<rr.high: sweep=(j,"short",b.high,b.low)
            else: continue
            break
        if sweep is None: continue
        j,side,extreme,break_level=sweep
        k=j+1
        if confirm=="mss":
            # Simple causal 15m microstructure proxy: break of sweep candle's opposite extreme.
            found=False
            for z in range(j+1,min(j+5,len(window)-1)):
                b=window.iloc[z]
                if (side=="long" and b.low<=extreme) or (side=="short" and b.high>=extreme): break
                if (side=="long" and b.close>break_level) or (side=="short" and b.close<break_level):
                    k=z+1; found=True; break
            if not found: continue
        if k>=len(window): continue
        et=window.index[k]; entry=float(window.iloc[k].open)
        stop=float(extreme); risk=entry-stop if side=="long" else stop-entry
        if risk<=0 or risk/entry>0.05: continue
        target=entry+(target_r*risk if side=="long" else -target_r*risk)
        # Exit no later than end of next reference interval. Do not allow overlapping positions.
        future=window.iloc[k:]
        if future.empty: continue
        outcome="TIME"; exitp=float(future.iloc[-1].close); exitt=future.index[-1]
        for t,b in future.iterrows():
            if (b.low<=stop if side=="long" else b.high>=stop):
                outcome="SL";exitp=stop;exitt=t;break
            if (b.high>=target if side=="long" else b.low<=target):
                outcome="TP";exitp=target;exitt=t;break
        gross=(exitp-entry)/risk if side=="long" else (entry-exitp)/risk
        cost=COST_RATE*entry/risk
        trades.append(dict(reference_tf=tf,confirm=confirm,target_r=target_r,
          session="all" if session is None else "london_ny",side=side,
          reference_time=rt,entry_time=et,exit_time=exitt,entry=entry,
          stop=stop,target=target,exit=exitp,outcome=outcome,net_R=gross-cost))
        locked_until=exitt+pd.Timedelta("15min")
    return trades
def main():
    exe=fetch("15m")
    exe=exe.sort_index()
    gaps=exe.index.to_series().diff().dropna()
    print("15m rows",len(exe),"gaps",int((gaps!=pd.Timedelta("15min")).sum()))
    alltr=[]
    for tf,rule in REFS.items():
        ref=ref_bars(exe,rule)
        # Reference must contain the full set of 15m bars.
        counts=exe["close"].resample(rule,label="left",closed="left").count()
        ref=ref.loc[counts.reindex(ref.index).eq(int(pd.Timedelta(tf)/pd.Timedelta("15min")))]
        for confirm in ("reclaim","mss"):
            for target in (1.5,2.0,3.0):
                for session in SESSIONS.values():
                    alltr.extend(test(exe,ref,tf,confirm,target,session))
    if not alltr: raise RuntimeError("No trades generated")
    d=pd.DataFrame(alltr).sort_values("entry_time")
    # Chronological split, NOT optimized on OOS. Keep all configurations.
    split=exe.index[int(len(exe)*0.7)]
    d["sample"]=np.where(d.entry_time<split,"train","test")
    d.to_csv(OUT/"crt_v2_trades.csv",index=False)
    rows=[]
    for key,g in d.groupby(["reference_tf","confirm","target_r","session","sample"]):
        r=g.net_R; wins=r[r>0]; losses=r[r<0]
        eq=r.cumsum(); dd=eq-eq.cummax()
        rows.append(dict(zip(["reference_tf","confirm","target_r","session","sample"],key)) |
          dict(trades=len(g),net_R=round(r.sum(),3),average_R=round(r.mean(),4),
          profitable_pct=round(100*(r>0).mean(),2),
          profit_factor=round(wins.sum()/abs(losses.sum()),3) if len(losses) else None,
          max_drawdown_R=round(min(0,dd.min()),3)))
    summary=pd.DataFrame(rows)
    summary.to_csv(OUT/"crt_v2_summary.csv",index=False)
    meta={"data_start":str(exe.index.min()),"data_end":str(exe.index.max()),
      "split":str(split),"rows":len(exe),"gaps":int((gaps!=pd.Timedelta("15min")).sum()),
      "estimated_round_trip_cost":COST_RATE,
      "limitations":["MSS is a candle-break proxy, not full swing-structure MSS",
      "No intrabar sequencing; SL first if both touched","Entry next candle open",
      "Time exit at end of next reference interval","No funding or slippage beyond cost assumption",
      "Selection among variants on test data would invalidate OOS claims"]}
    (OUT/"crt_v2_methodology.json").write_text(json.dumps(meta,indent=2))
    print("CRT V2 DATA",json.dumps(meta))
    print(summary.sort_values(["sample","net_R"],ascending=[True,False]).to_string(index=False))
if __name__=="__main__": main()
