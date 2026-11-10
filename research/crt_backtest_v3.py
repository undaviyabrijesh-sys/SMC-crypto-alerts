"""CRT v3 broad research matrix. Experimental; never changes production signals."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from crt_backtest import fetch, OUT

COST_RATE=0.0012
REFS={"1h":"1h","4h":"4h","daily":"1D","weekly":"W-MON"}
CONFIRMS=("reclaim","displacement","mss","mss_retest","mss_fvg")
SESSIONS={"all":None,"london_ny_utc":set(range(7,22))}
TARGETS=(1.5,2.0,3.0,4.0,"opposite_range")
BUFFERS=(0.0,0.1)

def resample(x,rule):
    z=x.resample(rule,label="left",closed="left").agg(
      {"open":"first","high":"max","low":"min","close":"last"}).dropna()
    tr=pd.concat([z.high-z.low,(z.high-z.close.shift()).abs(),
                  (z.low-z.close.shift()).abs()],axis=1).max(axis=1)
    z["atr"]=tr.rolling(14,min_periods=5).mean()
    return z

def choose_entry(w, sweep_i, side, extreme, confirm):
    # Sweep candle itself must close back within the reference range.
    if confirm=="reclaim": return sweep_i+1 if sweep_i+1<len(w) else None
    b=w.iloc[sweep_i]
    if confirm=="displacement":
        hist=w.iloc[max(0,sweep_i-20):sweep_i]
        if len(hist)<5: return None
        body=abs(float(b.close-b.open))
        med=float((hist.close-hist.open).abs().median())
        directional=(b.close>b.open) if side=="long" else (b.close<b.open)
        return sweep_i+1 if med>0 and body>=1.2*med and directional else None
    # Confirm break of sweep candle's opposite extreme (simple MSS proxy).
    level=float(b.high if side=="long" else b.low)
    mss_i=None
    for j in range(sweep_i+1,min(sweep_i+7,len(w))):
        c=w.iloc[j]
        if (side=="long" and c.close>level) or (side=="short" and c.close<level):
            mss_i=j; break
    if mss_i is None: return None
    if confirm=="mss": return mss_i+1 if mss_i+1<len(w) else None
    if confirm=="mss_retest":
        for j in range(mss_i+1,min(mss_i+5,len(w)-1)):
            c=w.iloc[j]
            if c.low<=level<=c.high: return j+1
        return None
    if confirm=="mss_fvg":
        # Three-candle imbalance after MSS; entry next bar after first valid FVG.
        for j in range(max(mss_i+1,2),min(mss_i+7,len(w)-1)):
            if side=="long" and w.iloc[j].low>w.iloc[j-2].high: return j+1
            if side=="short" and w.iloc[j].high<w.iloc[j-2].low: return j+1
        return None
    return None

def run_one(exe, ref, tf, confirm, target_mode, buffer_atr, reverse, session_name, session_hours):
    delta=pd.Timedelta(tf); lock=pd.Timestamp.min.tz_localize("UTC"); trades=[]
    for rt,rr in ref.iterrows():
        start=rt+delta; end=start+delta
        if start>=exe.index[-1] or start<=lock: continue
        w=exe.loc[(exe.index>=start)&(exe.index<end)]
        # Skip incomplete windows and windows containing missing 15m bars.
        expected=int(delta/pd.Timedelta("15min"))
        if len(w)!=expected or (w.index.to_series().diff().dropna()!=pd.Timedelta("15min")).any(): continue
        sig=None
        for i,b in enumerate(w.iloc[:-1].itertuples()):
            t=w.index[i]
            if session_hours is not None and t.hour not in session_hours: continue
            if b.low<rr.low and rr.low<b.close<rr.high: sig=(i,"long",float(b.low)); break
            if b.high>rr.high and rr.low<b.close<rr.high: sig=(i,"short",float(b.high)); break
        if sig is None: continue
        si,signal_side,extreme=sig
        ei=choose_entry(w,si,signal_side,extreme,confirm)
        if ei is None or ei>=len(w): continue
        entry=float(w.iloc[ei].open); et=w.index[ei]
        atr=float(rr.atr) if pd.notna(rr.atr) and rr.atr>0 else float(rr.high-rr.low)
        pad=buffer_atr*atr
        original_stop=extreme-pad if signal_side=="long" else extreme+pad
        risk=entry-original_stop if signal_side=="long" else original_stop-entry
        if risk<=0 or risk/entry>0.05: continue
        side=("short" if signal_side=="long" else "long") if reverse else signal_side
        stop=entry+risk if side=="short" else entry-risk
        if target_mode=="opposite_range":
            target=float(rr.high if side=="long" else rr.low)
        else:
            target=entry+(float(target_mode)*risk if side=="long" else -float(target_mode)*risk)
        if (side=="long" and target<=entry) or (side=="short" and target>=entry): continue
        future=w.iloc[ei:]
        if future.empty: continue
        outcome="TIME"; exitp=float(future.iloc[-1].close); exitt=future.index[-1]
        for t,b in future.iterrows():
            sl=(b.low<=stop) if side=="long" else (b.high>=stop)
            tp=(b.high>=target) if side=="long" else (b.low<=target)
            if sl: outcome="SL";exitp=stop;exitt=t;break
            if tp: outcome="TP";exitp=target;exitt=t;break
        gross=(exitp-entry)/risk if side=="long" else (entry-exitp)/risk
        net=gross-COST_RATE*entry/risk
        trades.append(dict(reference=tf,confirm=confirm,target=str(target_mode),
          buffer_atr=buffer_atr,direction="reversed" if reverse else "original",
          session=session_name,signal_side=signal_side,side=side,
          reference_time=rt,entry_time=et,exit_time=exitt,entry=entry,stop=stop,
          target_price=target,exit=exitp,outcome=outcome,gross_R=gross,
          cost_R=COST_RATE*entry/risk,net_R=net))
        lock=exitt+pd.Timedelta("15min")
    return trades

def main():
    exe=fetch("15m").sort_index()
    gap=exe.index.to_series().diff().dropna()
    split=exe.index[int(len(exe)*0.7)]
    alltr=[]
    for tf,rule in REFS.items():
        ref=resample(exe,rule)
        counts=exe.close.resample(rule,label="left",closed="left").count()
        ref=ref.loc[counts.reindex(ref.index).eq(int(pd.Timedelta(tf)/pd.Timedelta("15min")))]
        for confirm in CONFIRMS:
          for target in TARGETS:
           for buf in BUFFERS:
            for rev in (False,True):
             for sn,sh in SESSIONS.items():
              alltr.extend(run_one(exe,ref,tf,confirm,target,buf,rev,sn,sh))
    if not alltr: raise RuntimeError("No v3 trades produced")
    d=pd.DataFrame(alltr).sort_values("entry_time")
    d["sample"]=np.where(d.entry_time<split,"train","test")
    d.to_csv(OUT/"crt_v3_trades.csv",index=False)
    keys=["reference","confirm","target","buffer_atr","direction","session","sample"]
    rows=[]
    for k,g in d.groupby(keys):
        r=g.net_R; pos=r[r>0]; neg=r[r<0]; eq=r.cumsum(); dd=eq-eq.cummax()
        rows.append(dict(zip(keys,k))|dict(trades=len(g),profitable_pct=round(100*(r>0).mean(),2),
          profit_factor=round(pos.sum()/abs(neg.sum()),3) if len(neg) and neg.sum()!=0 else None,
          net_R=round(r.sum(),2),avg_R=round(r.mean(),3),max_drawdown_R=round(min(0,dd.min()),2),
          TP=int((g.outcome=="TP").sum()),SL=int((g.outcome=="SL").sum()),TIME=int((g.outcome=="TIME").sum())))
    s=pd.DataFrame(rows);s.to_csv(OUT/"crt_v3_summary.csv",index=False)
    meta={"rows_15m":len(exe),"start":str(exe.index.min()),"end":str(exe.index.max()),
      "gaps_15m":int((gap!=pd.Timedelta("15min")).sum()),"oos_split":str(split),
      "configurations":len(s),"round_trip_cost_assumption":COST_RATE,
      "notes":["MSS is a defined candle-break proxy, not discretionary swing-structure interpretation",
      "FVG is a mechanical 3-candle imbalance proxy","UTC 07:00-21:00 is a broad London/New York proxy; DST not modelled",
      "One trade at a time within each exact configuration; variants run independently",
      "Stop-first when SL and TP touch same 15m candle","No funding; cost is assumed not user fee-tier verified",
      "Opposite-range target can be invalid and those signals are skipped",
      "Daily and weekly reference ranges use completed bars only"]}
    (OUT/"crt_v3_methodology.json").write_text(json.dumps(meta,indent=2))
    print("CRT V3 META",json.dumps(meta))
    print("TOP TEST SETUPS")
    print(s[s["sample"]=="test"].sort_values("net_R",ascending=False).head(40).to_string(index=False))
    print("BOTTOM TEST SETUPS")
    print(s[s["sample"]=="test"].sort_values("net_R").head(20).to_string(index=False))
if __name__=="__main__": main()
