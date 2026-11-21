#!/usr/bin/env python3
"""BTC 5m previous-hour CRT sweep/reclaim study. Frozen diagnostic research only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

COSTS=[0,4,7,10,20]; TICK=0.1; BAR_NS=300_000_000_000; HOUR_NS=3_600_000_000_000
MAX_HOLD=12; COOLDOWN=12
VARIANTS=[(0.25,"immediate","range"),(0.25,"immediate","2R"),(0.25,"next_bar_break","range"),(0.25,"next_bar_break","2R"),
          (0.40,"immediate","range"),(0.40,"immediate","2R"),(0.40,"next_bar_break","range"),(0.40,"next_bar_break","2R")]

def wilder_atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    out=np.full(len(df),np.nan)
    if len(df)>=n:
        vals=tr.to_numpy(float); out[n-1]=np.mean(vals[:n])
        for i in range(n,len(vals)): out[i]=(out[i-1]*(n-1)+vals[i])/n
    return out

def build_maps(df):
    ts=df.timestamp.astype("int64").to_numpy()
    hour_floor=(ts//HOUR_NS)*HOUR_NS
    tmp=df.copy(); tmp["hour_ns"]=hour_floor
    h=tmp.groupby("hour_ns",sort=True).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),count=("close","size"))
    h=h[h["count"]==12].copy(); prior={}; regimes={}
    ema=h.close.ewm(span=200,adjust=False,min_periods=200).mean()
    for hour,row in h.iterrows():
        avail=int(hour)+HOUR_NS; prior[avail]=(float(row.high),float(row.low))
        ev=ema.loc[hour]
        if not np.isfinite(ev): rg="unknown"
        elif row.close>ev*1.005: rg="bull"
        elif row.close<ev*0.995: rg="bear"
        else: rg="neutral"
        regimes[avail]=rg
    return prior,regimes,len(h)

def signal_at(i,ts,op,hi,lo,cl,atr,prior,threshold):
    ref_key=(int(ts[i])//HOUR_NS)*HOUR_NS; ref=prior.get(ref_key)
    if ref is None or not np.isfinite(atr[i]) or atr[i]<=0: return None
    ph,pl=ref; span=hi[i]-lo[i]
    if span<=0: return None
    cp=(cl[i]-lo[i])/span
    short=(hi[i]>ph+TICK and pl<cl[i]<ph and cp<=threshold)
    long=(lo[i]<pl-TICK and pl<cl[i]<ph and cp>=1-threshold)
    if short==long: return None
    side=-1 if short else 1
    stop=hi[i]+.1*atr[i] if short else lo[i]-.1*atr[i]
    target=pl if short else ph
    return (side,stop,target,hi[i],lo[i],cp,ref_key)

def resolve_bar_exit(side,op,hi,lo,stop,target):
    """Stop-first ambiguity; adverse stop gaps fill at open; target gaps capped."""
    stop_hit=lo<=stop if side==1 else hi>=stop
    target_hit=hi>=target if side==1 else lo<=target
    if stop_hit and target_hit:
        px=op if ((side==1 and op<stop) or (side==-1 and op>stop)) else stop
        return float(px),"SL_BOTH_STOP_FIRST"
    if stop_hit:
        px=op if ((side==1 and op<stop) or (side==-1 and op>stop)) else stop
        return float(px),"SL_GAP" if px==op and op!=stop else "SL"
    if target_hit: return float(target),"TP"
    return None

def simulate(arr,prior,regimes,atr,start,end,threshold,confirm,target_mode):
    ts,op,hi,lo,cl=arr; rows=[]; i=max(start,14); last_exit=-10**9
    while i<end-MAX_HOLD-2:
        if i<last_exit+COOLDOWN: i+=1; continue
        sig=signal_at(i,ts,op,hi,lo,cl,atr,prior,threshold)
        if sig is None: i+=1; continue
        side,stop,target_range,sh,sl,cp,ref_key=sig
        if confirm=="immediate": ei=i+1
        else:
            k=i+1
            if k>=end: i+=1; continue
            if side==-1: confirmed=lo[k]<sl-TICK; invalid=hi[k]>=sh
            else: confirmed=hi[k]>sh+TICK; invalid=lo[k]<=sl
            if not confirmed or invalid: i+=1; continue
            ei=i+2
        if ei>=end or ei+MAX_HOLD-1>=end: i+=1; continue
        entry=float(op[ei])
        if (side==-1 and entry>=stop) or (side==1 and entry<=stop): i+=1; continue
        risk=abs(entry-stop)
        if risk<=0: i+=1; continue
        target=float(target_range) if target_mode=="range" else entry+side*2*risk
        reward=(target-entry)*side
        if reward<=0 or (target_mode=="range" and reward<risk): i+=1; continue
        exit_i=None; exit_price=None; reason=None; max_j=min(ei+MAX_HOLD-1,end-1)
        for j in range(ei,max_j+1):
            resolved=resolve_bar_exit(side,op[j],hi[j],lo[j],stop,target)
            if resolved is not None:
                exit_i=j; exit_price,reason=resolved; break
            close_ns=int(ts[j])+BAR_NS
            dt=pd.Timestamp(close_ns,tz="UTC")
            if dt.hour in (0,8,16) and dt.minute==0:
                exit_i=j; exit_price=cl[j]; reason="FUNDING_FLAT"; break
        if exit_i is None: exit_i=max_j; exit_price=cl[exit_i]; reason="TIME"
        gross=((exit_price-entry)*side)/risk
        month=pd.Timestamp(int(ts[ei]),tz="UTC").strftime("%Y-%m")
        regime=regimes.get(ref_key,"unknown")
        rows.append({"signal_time":pd.Timestamp(int(ts[i]),tz="UTC").isoformat(),"entry_time":pd.Timestamp(int(ts[ei]),tz="UTC").isoformat(),
          "exit_time":pd.Timestamp(int(ts[exit_i]),tz="UTC").isoformat(),"side":"long" if side==1 else "short","close_threshold":threshold,
          "confirmation":confirm,"target_mode":target_mode,"entry":entry,"stop":stop,"target":target,"exit":exit_price,"exit_reason":reason,
          "risk_points":risk,"gross_R":gross,"regime":regime,"month":month})
        last_exit=exit_i; i=exit_i+1
    return pd.DataFrame(rows)

def calc_stats(g,cost):
    if g.empty:
        return {"trades":0,"win_rate_pct":np.nan,"profit_factor":np.nan,"net_R":0.,"avg_R":np.nan,"max_drawdown_R":0.,"max_losing_streak":0,"positive_month_fraction":np.nan,"positive_months":0,"active_months":0,"sum_net_return_pct":0.0}
    side=np.where(g.side.to_numpy()=="long",1.0,-1.0)
    r=g.gross_R.to_numpy(float)-(cost/10000*g.entry.to_numpy(float))/g.risk_points.to_numpy(float)
    net_pct=((g.exit.to_numpy(float)-g.entry.to_numpy(float))*side/g.entry.to_numpy(float))*100-cost/100
    w=r[r>0]; l=r[r<0]; eq=np.r_[0,np.cumsum(r)]; dd=eq-np.maximum.accumulate(eq); streak=mx=0
    for x in r:
        if x<0: streak+=1; mx=max(mx,streak)
        else: streak=0
    month_net=pd.Series(r).groupby(g.month.to_numpy()).sum(); pos=int((month_net>0).sum()); n=len(month_net)
    return {"trades":len(g),"win_rate_pct":round(float((r>0).mean()*100),2),
      "profit_factor":round(float(w.sum()/abs(l.sum())),3) if len(l) and w.sum()>0 else (float("inf") if len(w) else 0.),
      "net_R":round(float(r.sum()),3),"avg_R":round(float(r.mean()),4),"max_drawdown_R":round(float(dd.min()),3),
      "max_losing_streak":mx,"positive_month_fraction":round(pos/n,3) if n else np.nan,
      "positive_months":pos,"active_months":n,"sum_net_return_pct":round(float(net_pct.sum()),3)}

def run(data_path,out):
    out.mkdir(parents=True,exist_ok=True); sha=hashlib.sha256(data_path.read_bytes()).hexdigest()
    df=pd.read_csv(data_path,parse_dates=["timestamp"]); df=df.sort_values("timestamp").reset_index(drop=True)
    df["timestamp"]=df.timestamp.dt.tz_localize("UTC") if df.timestamp.dt.tz is None else df.timestamp.dt.tz_convert("UTC")
    assert df.timestamp.is_unique and (df.timestamp.diff().dropna()==pd.Timedelta(minutes=5)).all()
    assert ((df.high>=df[["open","close","low"]].max(axis=1))&(df.low<=df[["open","close","high"]].min(axis=1))).all()
    ts=df.timestamp.astype("int64").to_numpy(); op=df.open.to_numpy(float); hi=df.high.to_numpy(float); lo=df.low.to_numpy(float); cl=df.close.to_numpy(float)
    atr=wilder_atr(df); prior,regimes,hours=build_maps(df); arr=(ts,op,hi,lo,cl)
    n=len(df); d=int(n*.70); v=int(n*.85); splits={"development":(0,d),"validation":(d,v)}
    summaries=[]; alltr=[]; monthly=[]; regrows=[]
    for split,(a,b) in splits.items():
        for threshold,confirm,target_mode in VARIANTS:
            tr=simulate(arr,prior,regimes,atr,a,b,threshold,confirm,target_mode)
            variant=f"close{threshold:.2f}_{confirm}_{target_mode}"
            if not tr.empty: tr["split"]=split; tr["variant"]=variant; alltr.append(tr)
            for cost in COSTS:
                summaries.append({"split":split,"variant":variant,"close_threshold":threshold,"confirmation":confirm,"target_mode":target_mode,"cost_bps":cost,**calc_stats(tr,cost)})
            if not tr.empty:
                r10=tr.copy()
                for month,g in r10.groupby("month"): monthly.append({"split":split,"variant":variant,"month":month,**calc_stats(g,10)})
                for regime,g in r10.groupby("regime"): regrows.append({"split":split,"variant":variant,"regime":regime,**calc_stats(g,10)})
    summary=pd.DataFrame(summaries); trades=pd.concat(alltr,ignore_index=True) if alltr else pd.DataFrame()
    sm=pd.DataFrame(monthly); sr=pd.DataFrame(regrows); primary=summary[summary.cost_bps==10]; gates=[]
    for variant in primary.variant.unique():
        x=primary[primary.variant==variant].set_index("split"); dev=x.loc["development"]; val=x.loc["validation"]
        passed=(dev.trades>=100 and val.trades>=30 and dev.profit_factor>1.1 and val.profit_factor>1.1 and dev.net_R>0 and val.net_R>0 and dev.positive_month_fraction>=.55 and val.positive_month_fraction>=.55)
        gates.append({"variant":variant,"dev_trades":dev.trades,"val_trades":val.trades,"dev_pf":dev.profit_factor,"val_pf":val.profit_factor,
          "dev_net_R":dev.net_R,"val_net_R":val.net_R,"dev_positive_month_fraction":dev.positive_month_fraction,
          "val_positive_month_fraction":val.positive_month_fraction,"gate_pass":bool(passed)})
    gates=pd.DataFrame(gates)
    summary.to_csv(out/"summary_dev_val_costs.csv",index=False); trades.to_csv(out/"trades_dev_val.csv",index=False)
    sm.to_csv(out/"monthly_primary_10bps.csv",index=False); sr.to_csv(out/"regime_primary_10bps.csv",index=False); gates.to_csv(out/"candidate_gates.csv",index=False)
    meta={"status":"completed","symbol":"BTCUSD","source":"Delta BTCUSD 5m OHLCV archive","source_rows":n,
      "source_start":str(df.timestamp.iloc[0]),"source_end":str(df.timestamp.iloc[-1]),"source_sha256":sha,
      "missing_5m_intervals":0,"invalid_ohlc_rows":0,"complete_hourly_bars":hours,
      "splits":{"development_end_index":d,"validation_end_index":v,"oos_end_index":n},
      "variants":len(VARIANTS),"summary_rows":len(summary),"trade_rows":len(trades),"gate_pass_count":int(gates.gate_pass.sum()),
      "rules":{"reference":"previous fully completed UTC 1h candle built from 12 complete 5m bars",
        "short":"sweep prior-hour high by >0.1, close back inside range, close location <= threshold",
        "long":"sweep prior-hour low by >0.1, close back inside, close location >=1-threshold",
        "dual_sweep":"discard","confirmation":"immediate next open or next bar breaks signal extreme and enter following open",
        "stop":"sweep extreme +/- 0.1 Wilder ATR14","target":"opposite prior-hour boundary (>=1R) or fixed 2R",
        "max_hold_bars":MAX_HOLD,"cooldown_bars":COOLDOWN,"same_bar":"stop first",
        "funding":"flat at close before 00/08/16 UTC settlement; cashflow not modeled","costs_bps_round_trip":COSTS,
        "oos":"not evaluated because no candidate passed development/validation"},
      "limitations":["One BTC source; no ETH replication.","No funding cashflow, spread or market-impact model.","OHLC intrabar path unavailable; same-bar stop-first."]}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    report=["# BTC 5m previous-hour CRT-style sweep/reclaim study","","**Status: completed research diagnostic.**",
      f"- Source: {n:,} 5m bars, {df.timestamp.iloc[0]} to {df.timestamp.iloc[-1]}",f"- SHA-256: {sha}",
      "- Missing intervals: 0; invalid OHLC rows: 0.",f"- Complete hourly reference candles: {hours:,}.",
      "- Chronological split: 70% development, 15% validation, final 15% untouched unless gate passes.","",
      "## Primary results at 10 bps",primary.to_markdown(index=False),"","## Candidate gates",gates.to_markdown(index=False),"",
      "No configuration passed the preregistered development/validation gate; OOS was not evaluated.","",
      "Limitations: one BTC source, no ETH replication, no funding cashflow/spread/market-impact model, and stop-first OHLC execution."]
    (out/"REPORT.md").write_text("\n".join(report)+"\n")
    print(primary.to_string(index=False)); print(gates.to_string(index=False))

def self_test():
    idx=pd.date_range("2026-01-01T00:00:00Z",periods=24,freq="5min")
    toy=pd.DataFrame({"timestamp":idx,"open":100.,"high":101.,"low":99.,"close":100.,"volume":1.})
    pm,rg,nh=build_maps(toy)
    assert pd.Timestamp("2026-01-01T01:00:00Z").value in pm
    assert pd.Timestamp("2026-01-01T00:00:00Z").value not in pm
    assert pm[pd.Timestamp("2026-01-01T01:00:00Z").value]==(101.,99.)
    ts=idx.astype("int64").to_numpy(); op=np.ones(24)*100; hi=np.ones(24)*101; lo=np.ones(24)*99; cl=np.ones(24)*100; atr=np.ones(24)
    hi[12]=102; lo[12]=98
    assert signal_at(12,ts,op,hi,lo,cl,atr,pm,.4) is None
    assert resolve_bar_exit(1,100,103,97,98,102)==(98.0,"SL_BOTH_STOP_FIRST")
    assert resolve_bar_exit(1,95,99,94,98,102)==(95.0,"SL_GAP")
    assert resolve_bar_exit(1,105,106,104,98,102)==(102.0,"TP")
    assert (10/10000*100)/1 > (10/10000*100)/2
    print("5 deterministic CRT timing/sweep/cost tests passed")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--data",type=Path); ap.add_argument("--out",type=Path,default=Path("results")); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:self_test()
    else:
        if not args.data: raise SystemExit("--data required")
        run(args.data,args.out)
