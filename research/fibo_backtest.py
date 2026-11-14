"""Fibonacci retracement BTCUSD research. Confirmed 1H pivots; 15m execution; no future swing leakage."""
import time, json, hashlib
from pathlib import Path
import requests
import numpy as np
import pandas as pd

BASE="https://api.india.delta.exchange/v2/history/candles"
SYMBOL="BTCUSD"; DAYS=730; OUT=Path("fibo_results"); OUT.mkdir(exist_ok=True)
COST=0.0012; PIVOT_L=3; PIVOT_R=3
ENTRY_MODES=("0.50","0.618","zone")
CONFIRMS=("rejection","engulfing","break_prev")
STOPS=("swing","0.786")
TARGETS=("1.272","1.618","2R")
def fetch():
    step=900; end=int(pd.Timestamp.now(tz="UTC").timestamp()); start=end-DAYS*86400
    frames=[]; cur=start
    while cur<end:
        stop=min(cur+step*1800,end)
        r=requests.get(BASE,params={"resolution":"15m","symbol":SYMBOL,"start":cur,"end":stop},timeout=40,
          headers={"Accept":"application/json","User-Agent":"SaltyQuantFibo/1.0"})
        r.raise_for_status(); p=r.json()
        if p.get("success") is not True: raise RuntimeError(f"Delta API error: {p}")
        if p.get("result"): frames.append(pd.DataFrame(p["result"]))
        cur=stop; time.sleep(.08)
    if not frames: raise RuntimeError("No candles returned")
    d=pd.concat(frames,ignore_index=True); d["timestamp"]=pd.to_datetime(pd.to_numeric(d.time),unit="s",utc=True)
    d=d.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    for c in ("open","high","low","close"): d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=["open","high","low","close"])
    d=d[(d.high>=d[["open","close","low"]].max(axis=1))&(d.low<=d[["open","close","high"]].min(axis=1))]
    d=d[d.index+pd.Timedelta("15min")<=pd.Timestamp.now(tz="UTC")]
    return d
def confirmed_pivots(h):
    out=[]
    H=h.high.to_numpy(); L=h.low.to_numpy(); ix=h.index
    for i in range(PIVOT_L,len(h)-PIVOT_R):
        # Reject pivot windows that bridge missing 1H candles.
        window=ix[i-PIVOT_L:i+PIVOT_R+1]
        if (window.to_series().diff().dropna()!=pd.Timedelta("1h")).any(): continue
        # Strict pivot; confirmation is available only after right-hand bars close.
        is_high=(H[i]>=max(H[i-PIVOT_L:i+PIVOT_R+1]) and H[i]>max(H[i-PIVOT_L:i]) and H[i]>max(H[i+1:i+PIVOT_R+1]))
        is_low=(L[i]<=min(L[i-PIVOT_L:i+PIVOT_R+1]) and L[i]<min(L[i-PIVOT_L:i]) and L[i]<min(L[i+1:i+PIVOT_R+1]))
        # A single wide candle cannot be both anchors in the same pivot sequence.
        if is_high and not is_low:
            out.append((ix[i+PIVOT_R]+pd.Timedelta("1h"),ix[i],"H",float(H[i])))
        elif is_low and not is_high:
            out.append((ix[i+PIVOT_R]+pd.Timedelta("1h"),ix[i],"L",float(L[i])))
    return sorted(out,key=lambda x:x[0])
def make_legs(h):
    piv=confirmed_pivots(h); legs=[]
    for i,(a,b) in enumerate(zip(piv,piv[1:])):
        # A leg expires when the next pivot is confirmed; stale fib levels are not tradable.
        valid_until=piv[i+2][0] if i+2<len(piv) else h.index[-1]+pd.Timedelta("1h")
        if a[2]=="L" and b[2]=="H" and b[3]>a[3]:
            legs.append(dict(available=b[0],valid_until=valid_until,direction="long",low=a[3],high=b[3],pivot_low=a[1],pivot_high=b[1]))
        elif a[2]=="H" and b[2]=="L" and b[3]<a[3]:
            legs.append(dict(available=b[0],valid_until=valid_until,direction="short",low=b[3],high=a[3],pivot_low=b[1],pivot_high=a[1]))
    return legs
def build_trades(x,legs,entry_mode,confirm,stop_mode,target_mode):
    trades=[]; locked_until=x.index[0]-pd.Timedelta("1min")
    for leg in legs:
        start=max(leg["available"],leg["pivot_high"],leg["pivot_low"])
        # The fib leg is valid only until the next confirmed pivot changes structure.
        w=x.loc[(x.index>=start)&(x.index<leg["valid_until"])]
        if len(w)<3: continue
        lo,hi=leg["low"],leg["high"]; span=hi-lo
        if span<=0: continue
        long=leg["direction"]=="long"
        levels=({".50":hi-.5*span,".618":hi-.618*span} if long else {".50":lo+.5*span,".618":lo+.618*span})
        if entry_mode=="0.50": zlo=zhi=levels[".50"]
        elif entry_mode=="0.618": zlo=zhi=levels[".618"]
        else: zlo,zhi=sorted([levels[".50"],levels[".618"]])
        for i in range(1,len(w)-1):
            t=w.index[i]
            if t<=locked_until: continue
            b=w.iloc[i]; prev=w.iloc[i-1]
            touched=(b.low<=zhi and b.high>=zlo) if long else (b.high>=zlo and b.low<=zhi)
            if not touched: continue
            if confirm=="rejection":
                ok=(b.close>b.open and b.close>zlo) if long else (b.close<b.open and b.close<zhi)
            elif confirm=="engulfing":
                ok=(b.close>b.open and b.open<=prev.close and b.close>=prev.open) if long else (b.close<b.open and b.open>=prev.close and b.close<=prev.open)
            else:
                # Confirmation occurs on a later candle after the zone touch.
                ok=False
                for j in range(i+1,min(i+5,len(w)-1)):
                    q=w.iloc[j]
                    if (long and q.close>w.iloc[j-1].high) or ((not long) and q.close<w.iloc[j-1].low):
                        i=j; b=q; t=w.index[j]; ok=True; break
            if not ok: continue
            entry=float(w.loc[t:].iloc[1].open); et=w.loc[t:].index[1]
            stop=(lo if long else hi) if stop_mode=="swing" else (hi-.786*span if long else lo+.786*span)
            risk=(entry-stop) if long else (stop-entry)
            if risk<=0 or risk/entry>.05: continue
            if target_mode=="2R": target=entry+(2*risk if long else -2*risk)
            else:
                ext=float(target_mode)
                target=(lo+ext*span) if long else (hi-ext*span)
                if (long and target<=entry) or ((not long) and target>=entry): continue
            # Set the time-exit from the bounded holding window, not the full remaining dataset.
            future=w.loc[(w.index>=et)&(w.index<et+pd.Timedelta("7D"))]
            if future.empty: continue
            outcome="TIME"; exitp=float(future.iloc[-1].close); exitt=future.index[-1]
            for ft,q in future.iterrows():
                sl=q.low<=stop if long else q.high>=stop
                tp=q.high>=target if long else q.low<=target
                if sl: outcome="SL";exitp=stop;exitt=ft;break
                if tp: outcome="TP";exitp=target;exitt=ft;break
            gross=(exitp-entry)/risk if long else (entry-exitp)/risk
            net=gross-COST*entry/risk
            trades.append(dict(direction=leg["direction"],entry_mode=entry_mode,confirm=confirm,stop_mode=stop_mode,target_mode=target_mode,
              available=leg["available"],entry_time=et,exit_time=exitt,entry=entry,stop=stop,target=target,exit=exitp,outcome=outcome,
              gross_R=gross,cost_R=COST*entry/risk,net_R=net))
            locked_until=exitt
            break
    return trades
def main():
    x=fetch(); x.to_csv(OUT/"BTCUSD_15m.csv")
    h=x.resample("1h",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    counts=x.close.resample("1h",label="left",closed="left").count(); h=h.loc[counts.reindex(h.index).eq(4)]
    legs=make_legs(h)
    if not legs: raise RuntimeError("No confirmed swing legs")
    split=x.index[int(len(x)*.7)]; rows=[]
    for em in ENTRY_MODES:
      for cf in CONFIRMS:
       for sm in STOPS:
        for tm in TARGETS:
         rows.extend(build_trades(x,legs,em,cf,sm,tm))
    if not rows: raise RuntimeError("No trades generated")
    d=pd.DataFrame(rows).sort_values("entry_time"); d["sample"]=np.where(d.entry_time<split,"train","test")
    d.to_csv(OUT/"fibo_trades.csv",index=False)
    keys=["direction","entry_mode","confirm","stop_mode","target_mode","sample"]; sums=[]
    def metrics(g):
        r=g.net_R; pos=r[r>0]; neg=r[r<0]; equity=r.cumsum().to_numpy(); dd=equity-np.maximum.accumulate(np.r_[0.0,equity])[1:]
        streak=best=0
        for v in r:
            streak=streak+1 if v<0 else 0
            best=max(best,streak)
        return dict(trades=len(g),win_pct=round((r>0).mean()*100,2),
          PF=round(pos.sum()/abs(neg.sum()),3) if len(neg) and neg.sum()!=0 else None,
          net_R=round(r.sum(),2),avg_R=round(r.mean(),3),max_DD_R=round(min(0,dd.min()),2),
          max_losing_streak=best,TP=int((g.outcome=="TP").sum()),SL=int((g.outcome=="SL").sum()),TIME=int((g.outcome=="TIME").sum()))
    for k,g in d.groupby(keys,sort=False):
        sums.append(dict(zip(keys,k))|metrics(g))
    s=pd.DataFrame(sums); s.to_csv(OUT/"fibo_summary.csv",index=False)
    monthly=[]
    for k,g in d.assign(month=d.entry_time.dt.strftime("%Y-%m")).groupby(keys+["month"],sort=False):
        monthly.append(dict(zip(keys+["month"],k))|metrics(g))
    pd.DataFrame(monthly).to_csv(OUT/"fibo_monthly.csv",index=False)
    meta={"symbol":SYMBOL,"rows_15m":len(x),"start":str(x.index.min()),"end":str(x.index.max()),
      "gaps_15m":int((x.index.to_series().diff().dropna()!=pd.Timedelta("15min")).sum()),
      "confirmed_1h_pivots":len(confirmed_pivots(h)),"swing_legs":len(legs),"oos_split":str(split),
      "round_trip_cost_assumption":COST,"pivot_left_right_bars":[PIVOT_L,PIVOT_R],
      "notes":["1H pivots become usable only after three subsequent contiguous 1H bars close",
      "15m execution; one trade at a time per configuration","Each fib leg expires when the next pivot is confirmed",
      "SL assumed first if stop and target touch in same 15m bar","7-day maximum holding period with time exit at last bar within that window",
      "12bp round-trip cost is an estimate, not user fee-tier verified",
      "No funding; spread and slippage are represented only by the assumed 12bp cost",
      "OOS is chronological final 30%; variants are independent",
      "Fibonacci leg is last consecutive confirmed alternating 1H pivot pair; no discretionary trend filter",
      "Monthly performance and maximum consecutive losing trades are included in outputs"]}
    (OUT/"fibo_methodology.json").write_text(json.dumps(meta,indent=2))
    print("FIBO META",json.dumps(meta)); print("TOP OOS")
    print(s[s["sample"]=="test"].sort_values("net_R",ascending=False).head(30).to_string(index=False))
    print("BOTTOM OOS")
    print(s[s["sample"]=="test"].sort_values("net_R").head(10).to_string(index=False))
if __name__=="__main__": main()
