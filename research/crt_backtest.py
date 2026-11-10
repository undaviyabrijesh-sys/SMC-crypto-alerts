"""Exploratory CRT backtest on public Delta Exchange India BTCUSD candles.
Signals use closed reference candles and 15m sweep/reclaim closes; entry is next 15m open.
Same-bar SL/TP ambiguity is resolved as SL first. Results are research, not a validated edge.
"""
import time, hashlib, json
from pathlib import Path
import requests
import pandas as pd
import numpy as np

BASE = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL = "BTCUSD"
DAYS = 730
OUT = Path("crt_results")
OUT.mkdir(exist_ok=True)
HEADERS = {"Accept": "application/json", "User-Agent": "SaltyQuantCRT/1.0"}
MINS = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

def fetch(tf):
    step = MINS[tf] * 60
    end = int(pd.Timestamp.now(tz="UTC").timestamp())
    start = end - DAYS * 86400
    frames = []
    # Keep each request below Delta's 2,000-candle limit.
    chunk = step * 1800
    cursor = start
    while cursor < end:
        stop = min(cursor + chunk, end)
        r = requests.get(BASE, params={"resolution": tf, "symbol": SYMBOL,
                         "start": cursor, "end": stop}, headers=HEADERS, timeout=40)
        r.raise_for_status()
        p = r.json()
        if p.get("success") is not True:
            raise RuntimeError(f"Delta API error {tf}: {p}")
        rows = p.get("result") or []
        if rows:
            frames.append(pd.DataFrame(rows))
        cursor = stop
        time.sleep(0.08)
    if not frames:
        raise RuntimeError(f"No candles returned for {tf}")
    d = pd.concat(frames, ignore_index=True)
    d["timestamp"] = pd.to_datetime(pd.to_numeric(d["time"]), unit="s", utc=True)
    d = d.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    for c in ["open","high","low","close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open","high","low","close"])
    d = d[(d.high >= d[["open","close","low"]].max(axis=1)) &
          (d.low <= d[["open","close","high"]].min(axis=1))]
    # Discard current, not-yet-closed candle.
    now = pd.Timestamp.now(tz="UTC")
    d = d[d.index + pd.Timedelta(minutes=MINS[tf]) <= now]
    d.to_csv(OUT / f"BTCUSD_{tf}.csv")
    return d

def backtest(ref, exe, target_mode, buffer_atr=False):
    # Each fully closed reference candle is tested only after its close.
    ref = ref.copy()
    ref["atr"] = (ref.high-ref.low).rolling(14).mean()
    trades=[]
    idx = exe.index
    for i, (rt, rr) in enumerate(ref.iterrows()):
        range_end = rt + pd.Timedelta(minutes= MINS[ref.attrs["tf"]])
        next_end = range_end + pd.Timedelta(minutes=MINS[ref.attrs["tf"]])
        lo = idx.searchsorted(range_end, side="left")
        hi = idx.searchsorted(next_end, side="left")
        if hi <= lo+1: continue
        bars = exe.iloc[lo:hi]
        if len(bars)<2: continue
        side = None
        for j in range(len(bars)-1):
            b=bars.iloc[j]
            # sweep through one edge and close back inside the reference range
            if b.low < rr.low and rr.low < b.close < rr.high:
                side="long"; extreme=float(b.low); entry=float(bars.iloc[j+1].open); et=bars.index[j+1]; break
            if b.high > rr.high and rr.low < b.close < rr.high:
                side="short"; extreme=float(b.high); entry=float(bars.iloc[j+1].open); et=bars.index[j+1]; break
        if not side or not np.isfinite(entry): continue
        atr=float(rr.atr) if pd.notna(rr.atr) else float(rr.high-rr.low)
        pad=0.1*atr if buffer_atr else 0.0
        stop=extreme-pad if side=="long" else extreme+pad
        risk=entry-stop if side=="long" else stop-entry
        if risk<=0 or risk/entry>0.05: continue
        if target_mode=="range":
            target=float(rr.high if side=="long" else rr.low)
        else:
            mult=float(target_mode)
            target=entry + (mult*risk if side=="long" else -mult*risk)
        if (side=="long" and target<=entry) or (side=="short" and target>=entry): continue
        outcome="TIME"; exitp=float(bars.iloc[-1].close); exitt=bars.index[-1]
        future=exe.loc[et:next_end]
        for ft, fb in future.iterrows():
            sl_hit = fb.low<=stop if side=="long" else fb.high>=stop
            tp_hit = fb.high>=target if side=="long" else fb.low<=target
            if sl_hit: outcome="SL"; exitp=stop; exitt=ft; break
            if tp_hit: outcome="TP"; exitp=target; exitt=ft; break
        gross=((exitp-entry)/risk) if side=="long" else ((entry-exitp)/risk)
        # Transparent conservative friction assumption: 0.06% each side, expressed in R.
        cost=(entry*0.0012)/risk
        trades.append({"reference_tf":ref.attrs["tf"],"target":target_mode,
          "atr_buffer":buffer_atr,"side":side,"reference_time":rt,"entry_time":et,
          "entry":entry,"stop":stop,"target_price":target,"exit_time":exitt,
          "exit":exitp,"outcome":outcome,"gross_R":gross,"estimated_cost_R":cost,
          "net_R":gross-cost})
    return pd.DataFrame(trades)

def main():
    data={tf:fetch(tf) for tf in MINS}
    # Validate continuity and report missing intervals rather than filling them.
    coverage=[]
    for tf,d in data.items():
        dif=d.index.to_series().diff().dropna()
        expected=pd.Timedelta(minutes=MINS[tf])
        coverage.append({"timeframe":tf,"rows":len(d),"start":str(d.index.min()),
          "end":str(d.index.max()),"gaps":int((dif!=expected).sum()),
          "largest_gap_minutes":float(dif.max().total_seconds()/60) if len(dif) else 0,
          "sha256":hashlib.sha256((OUT/f"BTCUSD_{tf}.csv").read_bytes()).hexdigest()})
    exe=data["15m"]
    alltr=[]
    for tf in ["1h","4h","1d"]:
        r=data[tf].copy(); r.attrs["tf"]=tf
        for target in ["1.5","2","3","range"]:
            for buff in [False,True]:
                t=backtest(r,exe,target,buff)
                if not t.empty: alltr.append(t)
    trades=pd.concat(alltr,ignore_index=True) if alltr else pd.DataFrame()
    if trades.empty:
        raise RuntimeError("No CRT trades found; inspect data and signal definitions.")
    trades.to_csv(OUT/"crt_trades.csv",index=False)
    summaries=[]
    keys=["reference_tf","target","atr_buffer"]
    for k,g in trades.groupby(keys):
        r=g.net_R
        wins=r[r>0]; losses=r[r<0]
        eq=r.cumsum(); dd=eq-eq.cummax()
        summaries.append(dict(zip(keys,k)) | {
          "trades":len(g),"win_rate_pct":round((g.outcome=="TP").mean()*100,2),
          "profit_factor":round(wins.sum()/abs(losses.sum()),3) if len(losses) and abs(losses.sum()) else None,
          "net_R":round(r.sum(),2),"avg_R":round(r.mean(),3),
          "max_drawdown_R":round(dd.min(),2),
          "long_trades":int((g.side=="long").sum()),"short_trades":int((g.side=="short").sum()),
          "TP":int((g.outcome=="TP").sum()),"SL":int((g.outcome=="SL").sum()),
          "TIME":int((g.outcome=="TIME").sum())})
    summary=pd.DataFrame(summaries).sort_values("net_R",ascending=False)
    summary.to_csv(OUT/"crt_summary.csv",index=False)
    (OUT/"data_quality.json").write_text(json.dumps(coverage,indent=2))
    print("DATA QUALITY"); print(pd.DataFrame(coverage).to_string(index=False))
    print("\nCRT SUMMARY (exploratory; estimated 12bp round-trip costs)"); print(summary.to_string(index=False))
    print(f"\nArtifacts: {OUT}/crt_summary.csv, crt_trades.csv, data_quality.json")

if __name__=="__main__": main()
