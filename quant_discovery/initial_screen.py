"""Reproducible exploratory OHLCV screen; never feeds production alerts.

Extract the verified archive into historical_data/, then run:
    python quant_discovery/initial_screen.py --data-dir historical_data

Fixed hypotheses only; historical funding is unavailable and is stress-tested,
not represented as observed data.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

TIMEFRAMES={"15m":(15,"1h"),"1h":(60,"4h")}
TF_MINUTES={"15m":15,"1h":60,"4h":240,"1d":1440,"1w":10080}
FUNDING_STRESS_BPS_PER_8H=1.0
TARGET_R=2.0

def validate_archive(root: Path):
    root=Path(root)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    validation=json.loads((root/"archive_validation.json").read_text(encoding="utf-8"))
    datasets=manifest.get("datasets")
    if validation.get("status")!="passed" or validation.get("actual_dataset_count")!=18:
        raise ValueError("Archive validation must pass for all 18 datasets")
    if not isinstance(datasets,dict) or len(datasets)!=18:
        raise ValueError("Manifest must contain exactly 18 datasets")
    for item in datasets.values():
        path=root/item["csv_path"]
        if not path.is_file(): raise FileNotFoundError(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item.get("sha256"):
            raise ValueError(f"SHA-256 mismatch: {path.name}")
        if len(pd.read_csv(path))!=int(item.get("row_count",-1)):
            raise ValueError(f"Row-count mismatch: {path.name}")
    return manifest,validation

def load_frame(root,symbol,tf):
    x=pd.read_csv(Path(root)/f"{symbol}_{tf}.csv",parse_dates=["timestamp"]).set_index("timestamp")
    x.index=pd.to_datetime(x.index,utc=True)
    return x.sort_index()

def rsi(close,period=2):
    d=close.diff()
    g=d.clip(lower=0).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    l=(-d.clip(upper=0)).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    rs=g/l.replace(0,np.nan)
    return (100-100/(1+rs)).fillna(50)

def indicators(x):
    x=x.copy(); pc=x.close.shift(1)
    tr=pd.concat([x.high-x.low,(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    x["atr14"]=tr.rolling(14,min_periods=14).mean()
    x["atr50"]=tr.rolling(50,min_periods=50).mean()
    x["ema20"]=x.close.ewm(span=20,adjust=False,min_periods=20).mean()
    x["ema50"]=x.close.ewm(span=50,adjust=False,min_periods=50).mean()
    x["ema200"]=x.close.ewm(span=200,adjust=False,min_periods=200).mean()
    mid=x.close.rolling(20,min_periods=20).mean()
    sd=x.close.rolling(20,min_periods=20).std(ddof=0)
    x["bb_low"]=mid-2*sd; x["bb_high"]=mid+2*sd
    x["rsi2"]=rsi(x.close,2)
    x["volume_sma20"]=x.volume.rolling(20,min_periods=20).mean()
    x["prior_high20"]=x.high.rolling(20,min_periods=20).max().shift(1)
    x["prior_low20"]=x.low.rolling(20,min_periods=20).min().shift(1)
    x["prior_high10"]=x.high.rolling(10,min_periods=10).max().shift(1)
    x["prior_low10"]=x.low.rolling(10,min_periods=10).min().shift(1)
    x["atr_ratio"]=x.atr14/x.atr50.replace(0,np.nan)
    return x

def add_closed_htf_context(lower,higher,higher_minutes):
    """HTF values become visible only after the higher-timeframe candle closes."""
    h=higher[["ema50","ema200"]].copy()
    h["htf_close_time"]=h.index+pd.Timedelta(minutes=higher_minutes)
    h=h.reset_index(drop=True).sort_values("htf_close_time")
    lower_minutes=int((lower.index[1]-lower.index[0]).total_seconds()/60)
    left=lower.copy()
    left["signal_close_time"]=left.index+pd.Timedelta(minutes=lower_minutes)
    merged=pd.merge_asof(left.reset_index(names="timestamp").sort_values("signal_close_time"),
                         h,left_on="signal_close_time",right_on="htf_close_time",direction="backward")
    return merged.set_index("timestamp")

def build_signals(root,symbol,tf):
    minutes,htf_tf=TIMEFRAMES[tf]
    lower=indicators(load_frame(root,symbol,tf))
    higher=indicators(load_frame(root,symbol,htf_tf))
    x=add_closed_htf_context(lower,higher,TF_MINUTES[htf_tf])
    up=x.ema50_y>x.ema200_y; down=x.ema50_y<x.ema200_y
    sig={
      "sweep_reclaim":np.where((x.low<x.prior_low20)&(x.close>x.prior_low20)&
        (x.close>=x.low+.60*(x.high-x.low)),1,
        np.where((x.high>x.prior_high20)&(x.close<x.prior_high20)&
        (x.close<=x.low+.40*(x.high-x.low)),-1,0)),
      "trend_pullback":np.where(up&(x.low<=x.ema20)&(x.close>x.ema20)&(x.close>x.open),1,
        np.where(down&(x.high>=x.ema20)&(x.close<x.ema20)&(x.close<x.open),-1,0)),
      "donchian_breakout":np.where((x.close>x.prior_high20)&(x.volume>1.2*x.volume_sma20)&(x.atr_ratio>1),1,
        np.where((x.close<x.prior_low20)&(x.volume>1.2*x.volume_sma20)&(x.atr_ratio>1),-1,0)),
      "mean_reversion":np.where((x.close<x.bb_low)&(x.rsi2<5),1,
        np.where((x.close>x.bb_high)&(x.rsi2>95),-1,0)),
      "volatility_expansion":np.where((x.atr_ratio>1.3)&(x.close>x.prior_high10),1,
        np.where((x.atr_ratio>1.3)&(x.close<x.prior_low10),-1,0)),
    }
    return x,sig,minutes

def simulate(x,signal,strategy,minutes,start,end,target_r=TARGET_R,stop_scale=1.0):
    """Next-bar-open replay; same-bar SL/TP ambiguity resolves SL-first."""
    idx=x.index; op=x.open.to_numpy(float); hi=x.high.to_numpy(float)
    lo=x.low.to_numpy(float); cl=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float); ar=x.atr_ratio.to_numpy(float)
    e50=x.ema50_y.to_numpy(float); e200=x.ema200_y.to_numpy(float)
    signal=np.asarray(signal,dtype=int); out=[]
    i=max(start,205); end=min(end,len(x)-1)
    max_hold=max(1,int(24*60/minutes)); step=minutes*60
    while i<end:
        d=int(signal[i]); ent_i=i+1
        if d==0 or ent_i+max_hold-1>=end: i+=1; continue
        if (idx[ent_i]-idx[i]).total_seconds()>step*1.5: i+=1; continue
        a=float(atr[i]); entry=float(op[ent_i])
        if not math.isfinite(a) or a<=0 or abs(entry-float(cl[i]))>.5*a: i+=1; continue
        if strategy in ("sweep_reclaim","trend_pullback"):
            risk=entry-(float(lo[i])-.1*a) if d==1 else (float(hi[i])+.1*a)-entry
        else:
            risk=(1.5 if strategy in ("donchian_breakout","mean_reversion") else 1.2)*a
        risk*=stop_scale
        if not math.isfinite(risk) or risk<.5*a or risk>3*a: i+=1; continue
        stop=entry-d*risk; target=entry+d*target_r*risk
        last=min(end-1,ent_i+max_hold-1); exit_price=None; outcome=None; exit_i=None; prev=ent_i-1
        for j in range(ent_i,last+1):
            if (idx[j]-idx[prev]).total_seconds()>step*1.5:
                exit_price=float(op[j]); outcome="GAP"; exit_i=j; break
            o,h,l=float(op[j]),float(hi[j]),float(lo[j])
            if d==1:
                if o<=stop: exit_price,outcome=o,"SL"
                elif o>=target: exit_price,outcome=o,"TP"
                elif l<=stop: exit_price,outcome=stop,"SL"
                elif h>=target: exit_price,outcome=target,"TP"
            else:
                if o>=stop: exit_price,outcome=o,"SL"
                elif o<=target: exit_price,outcome=o,"TP"
                elif h>=stop: exit_price,outcome=stop,"SL"
                elif l<=target: exit_price,outcome=target,"TP"
            if outcome: exit_i=j; break
            prev=j
        if outcome is None: exit_i=last; exit_price=float(cl[last]); outcome="TIME"
        regime="UP" if np.isfinite(e50[i]) and e50[i]>e200[i] else (
               "DOWN" if np.isfinite(e50[i]) and e50[i]<e200[i] else "NEUTRAL")
        out.append({"entry_time":idx[ent_i],"exit_time":idx[exit_i],"entry":entry,
          "exit":float(exit_price),"risk":risk,"gross_R":d*(float(exit_price)-entry)/risk,
          "hold_hours":max(0,(idx[exit_i]-idx[ent_i]).total_seconds()/3600),
          "outcome":outcome,"regime":regime,
          "vol_regime":"HIGH" if np.isfinite(ar[i]) and ar[i]>1 else "LOW"})
        i=exit_i+1
    return out

def summarize(trades,months,cost_bps=10):
    if not trades:
        return {"n":0,"win_rate_pct":None,"expectancy_net_R":None,"profit_factor":None,
          "max_drawdown_R":None,"max_consecutive_losses":0,"trades_per_month":0,
          "TP":0,"SL":0,"TIME":0,"GAP":0}
    gross=np.array([t["gross_R"] for t in trades],float)
    holds=np.array([t["hold_hours"] for t in trades],float)
    entries=np.array([t["entry"] for t in trades],float)
    risks=np.array([t["risk"] for t in trades],float)
    cost=(cost_bps/10000+FUNDING_STRESS_BPS_PER_8H*(holds/8)/10000)*entries/risks
    net=gross-cost; wins=net[net>0]; losses=net[net<0]
    eq=np.cumsum(net); peak=np.maximum.accumulate(np.r_[0,eq])[1:]; dd=eq-peak
    streak=mx=0
    for v in net: streak=streak+1 if v<0 else 0; mx=max(mx,streak)
    return {"n":len(trades),"win_rate_pct":round(float((net>0).mean()*100),2),
      "expectancy_net_R":round(float(net.mean()),4),
      "profit_factor":round(float(wins.sum()/abs(losses.sum())),3) if len(losses) and abs(losses.sum()) else None,
      "max_drawdown_R":round(float(dd.min()),3),"max_consecutive_losses":int(mx),
      "trades_per_month":round(len(trades)/max(months,1e-9),2),
      "mean_hold_hours":round(float(holds.mean()),2),
      "TP":sum(t["outcome"]=="TP" for t in trades),"SL":sum(t["outcome"]=="SL" for t in trades),
      "TIME":sum(t["outcome"]=="TIME" for t in trades),"GAP":sum(t["outcome"]=="GAP" for t in trades),
      "gross_expectancy_R":round(float(gross.mean()),4)}

def run_experiments(data_dir,output_dir):
    validate_archive(data_dir); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    oos_rows=[]; split_rows=[]; regime_rows=[]; robust_rows=[]; walk_rows=[]
    for symbol in ("BTC","ETH","XAU"):
      for tf,(minutes,_) in TIMEFRAMES.items():
        x,signals,minutes=build_signals(data_dir,symbol,tf); n=len(x); c60=int(n*.6); c80=int(n*.8)
        folds=[("WF1",int(n*.5),int(n*.6)),("WF2",int(n*.6),int(n*.7)),
          ("WF3",int(n*.7),int(n*.8)),("WF4",int(n*.8),int(n*.9)),("WF5",int(n*.9),n)]
        for strategy,sig in signals.items():
          for split,a,b in (("TRAIN",0,c60),("VALIDATION",c60,c80),("OOS",c80,n)):
            months=max((x.index[b-1]-x.index[a]).total_seconds()/86400/30.4375,.1)
            trades=simulate(x,sig,strategy,minutes,a,b)
            split_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,"split":split,**summarize(trades,months,10)})
            if split!="OOS": continue
            oos_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,**summarize(trades,months,10)})
            for rg in ("UP","DOWN","NEUTRAL"):
              sub=[t for t in trades if t["regime"]==rg]
              regime_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,"regime":rg,**summarize(sub,months,10)})
            for rg in ("HIGH","LOW"):
              sub=[t for t in trades if t["vol_regime"]==rg]
              regime_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,"vol_regime":rg,**summarize(sub,months,10)})
            for cost in (5,10,20,40):
              split_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,
                "split":f"OOS_COST_{cost}BPS",**summarize(trades,months,cost)})
            for scale in (.8,1.0,1.2):
              for rr in (1.5,2.0,2.5):
                varied=simulate(x,sig,strategy,minutes,c80,n,target_r=rr,stop_scale=scale)
                robust_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,
                  "stop_scale":scale,"target_R":rr,**summarize(varied,months,10)})
          for fold,a,b in folds:
            months=max((x.index[b-1]-x.index[a]).total_seconds()/86400/30.4375,.1)
            trades=simulate(x,sig,strategy,minutes,a,b)
            walk_rows.append({"symbol":symbol,"timeframe":tf,"strategy":strategy,"fold":fold,
              "train_end":x.index[a-1].isoformat() if a else None,
              "test_start":x.index[a].isoformat(),"test_end":x.index[b-1].isoformat(),
              **summarize(trades,months,10)})
    outputs={"oos_summary":pd.DataFrame(oos_rows),"split_and_cost_summary":pd.DataFrame(split_rows),
      "oos_regime_summary":pd.DataFrame(regime_rows),"oos_parameter_robustness":pd.DataFrame(robust_rows),
      "walk_forward_summary":pd.DataFrame(walk_rows)}
    for name,table in outputs.items(): table.to_csv(output_dir/f"{name}.csv",index=False)
    return outputs

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",default="historical_data")
    parser.add_argument("--output-dir",default="quant_discovery/results")
    args=parser.parse_args(argv)
    out=run_experiments(Path(args.data_dir),Path(args.output_dir))
    print(out["oos_summary"].sort_values("expectancy_net_R").to_string(index=False))
    print(f"Saved {len(out)} result tables to {args.output_dir}")

if __name__=="__main__": main()
