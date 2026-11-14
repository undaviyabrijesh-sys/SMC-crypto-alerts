#!/usr/bin/env python3
"""Preregistered BTC OI-contraction + price-impulse execution study.

Research-only. Uses Delta BTCUSD traded-price 5m candles and 1h OI candles.
A signal is known only at the completed 1h close; entry is the next 5m open.
One frozen rule, no parameter search. Stop/target execution is resolved on 5m
OHLC with stop-first ambiguity handling. Funding is reported as unmodelled
because the archive's raw funding units/settlement semantics are not verified.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

BAR5 = pd.Timedelta(minutes=5)
BAR15 = pd.Timedelta(minutes=15)
BAR1H = pd.Timedelta(hours=1)
MAX_HOLD_BARS = 96
COOLDOWN = pd.Timedelta(hours=8)
LOOKBACK_HOURS = 168
MIN_LOOKBACK = 120
OI_Z_THRESHOLD = -1.5
PRICE_Q = 0.90
INITIAL_STOP_ATR15 = 1.5
TARGET_R = 2.0
COSTS_BPS = (6, 12, 20)

class StudyError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def load_ohlc(path: Path, label: str, allow_zero_low: bool=False) -> pd.DataFrame:
    d=pd.read_csv(path)
    if "timestamp" not in d.columns:
        raise StudyError(f"{label}: timestamp column missing")
    d["timestamp"]=pd.to_datetime(d.timestamp,utc=True,errors="raise")
    if d.timestamp.duplicated().any():
        raise StudyError(f"{label}: duplicate timestamps")
    d=d.sort_values("timestamp").set_index("timestamp")
    required=["open","high","low","close"]
    for c in required:
        d[c]=pd.to_numeric(d[c],errors="raise")
    if not np.isfinite(d[required].to_numpy(float)).all():
        raise StudyError(f"{label}: non-finite OHLC")
    positive_cols=["open","high","close"] if allow_zero_low else required
    if (d[positive_cols]<=0).any().any():
        raise StudyError(f"{label}: non-positive required OHLC")
    if allow_zero_low and (d.low<0).any():
        raise StudyError(f"{label}: negative low sentinel is invalid")
    bad=(d.high<d[["open","close","low"]].max(axis=1)) | (d.low>d[["open","close","high"]].min(axis=1))
    if bad.any():
        raise StudyError(f"{label}: invalid OHLC rows={int(bad.sum())}")
    return d

def segment_ids(index: pd.DatetimeIndex, step: pd.Timedelta) -> pd.Series:
    return index.to_series().diff().ne(step).cumsum().astype(int)

def complete_resample(d: pd.DataFrame, rule: str, expected: int, base_step: pd.Timedelta) -> pd.DataFrame:
    x=d.copy()
    x["segment"]=segment_ids(x.index,base_step).to_numpy()
    kw={"label":"right","closed":"left"}
    z=x[["open","high","low","close"]].resample(rule,**kw).agg(
        {"open":"first","high":"max","low":"min","close":"last"})
    counts=x.close.resample(rule,**kw).count()
    segs=x.segment.resample(rule,**kw).nunique()
    z=z.loc[counts.eq(expected)&segs.eq(1)].dropna()
    z["segment"]=segment_ids(z.index,pd.Timedelta(rule)).to_numpy()
    return z

def wilder_atr(d: pd.DataFrame, length: int=14) -> pd.Series:
    out=pd.Series(np.nan,index=d.index,dtype=float)
    for _,g in d.groupby("segment",sort=False):
        prev=g.close.shift(1)
        tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
        vals=tr.to_numpy(float); a=np.full(len(vals),np.nan)
        if len(vals)>=length and np.isfinite(vals[:length]).all():
            a[length-1]=float(vals[:length].mean())
            for i in range(length,len(vals)):
                a[i]=(a[i-1]*(length-1)+vals[i])/length
        out.loc[g.index]=a
    return out

def build_hourly_features(hourly: pd.DataFrame, oi: pd.DataFrame) -> pd.DataFrame:
    """Align OI candle close to its availability time and reset features at gaps/sentinels."""
    o=oi[["close"]].copy()
    o.index=o.index+BAR1H
    o=o.rename(columns={"close":"oi_close"})
    h=hourly[["open","high","low","close"]].join(o,how="left")
    valid=h.oi_close.notna() & (h.oi_close>0)
    price_gap=h.index.to_series().diff().ne(BAR1H)
    prev_valid=valid.shift(1,fill_value=False)
    h["segment"]=(price_gap | ~valid | ~prev_valid).cumsum().astype(int)
    h["oi_pct"]=np.nan; h["oi_z"]=np.nan; h["price_1h"]=np.nan
    h["q90_abs_price_1h"]=np.nan; h["trend24h"]=np.nan
    for _,g in h[valid].groupby("segment",sort=False):
        oi_pct=g.oi_close.pct_change(fill_method=None)
        price_ret=g.close.pct_change(fill_method=None)
        oi_roll=oi_pct.rolling(LOOKBACK_HOURS,min_periods=MIN_LOOKBACK)
        oi_mean=oi_roll.mean().shift(1)
        oi_std=oi_roll.std(ddof=0).shift(1).replace(0,np.nan)
        q90=price_ret.abs().rolling(LOOKBACK_HOURS,min_periods=MIN_LOOKBACK).quantile(PRICE_Q).shift(1)
        trend=g.close.pct_change(24,fill_method=None)
        h.loc[g.index,"oi_pct"]=oi_pct.to_numpy()
        h.loc[g.index,"oi_z"]=((oi_pct-oi_mean)/oi_std).to_numpy()
        h.loc[g.index,"price_1h"]=price_ret.to_numpy()
        h.loc[g.index,"q90_abs_price_1h"]=q90.to_numpy()
        h.loc[g.index,"trend24h"]=trend.to_numpy()
    h["regime"]=np.select(
        [h.trend24h>0.005,h.trend24h< -0.005],
        ["uptrend","downtrend"],default="range_or_unavailable")
    return h

def build_events(features: pd.DataFrame) -> pd.DataFrame:
    valid=(features.oi_pct<0)&(features.oi_z<=OI_Z_THRESHOLD)&(
        features.price_1h.abs()>=features.q90_abs_price_1h)
    e=features.loc[valid].copy()
    if e.empty:
        return pd.DataFrame(columns=["signal_time","side","oi_pct","oi_z","price_1h","regime","oi_spike"])
    e["signal_time"]=e.index
    e["side"]=np.where(e.price_1h>0,"long","short")
    e["oi_spike"]=e.oi_pct.abs()>0.20
    return e[["signal_time","side","oi_pct","oi_z","price_1h","q90_abs_price_1h","regime","oi_spike"]].reset_index(drop=True)

def resolve_bar(side: str, op: float, hi: float, lo: float, stop: float, target: float):
    """Return (fill, reason, ambiguous); stop wins if both levels trade."""
    if side=="long":
        sl=lo<=stop; tp=hi>=target
        if sl: return (min(op,stop) if op<stop else stop),"SL",bool(tp)
        if tp: return target,"TP",False
    else:
        sl=hi>=stop; tp=lo<=target
        if sl: return (max(op,stop) if op>stop else stop),"SL",bool(tp)
        if tp: return target,"TP",False
    return None,None,False

def make_periods(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    holdout_start=end-pd.DateOffset(months=6)
    first_val=start+pd.DateOffset(months=6)
    if first_val>=holdout_start:
        raise StudyError("Insufficient history for 6m train plus 6m final holdout")
    folds=[]; cursor=first_val; k=1
    while cursor<holdout_start:
        nxt=min(cursor+pd.DateOffset(months=2),holdout_start)
        folds.append({"name":f"validation_{k}","start":cursor,"end":nxt,
            "train_start":start,"train_end":cursor})
        cursor=nxt; k+=1
    return {"initial_train":{"name":"initial_train","start":start,"end":first_val},
        "validation_folds":folds,
        "final_holdout":{"name":"final_holdout","start":holdout_start,"end":end}}

def simulate_period(events: pd.DataFrame, bars5: pd.DataFrame, atr15: pd.Series,
                    start: pd.Timestamp, end: pd.Timestamp, label: str) -> pd.DataFrame:
    idx=bars5.index; op=bars5.open.to_numpy(float); hi=bars5.high.to_numpy(float)
    lo=bars5.low.to_numpy(float); cl=bars5.close.to_numpy(float)
    seg=segment_ids(idx,BAR5).to_numpy()
    rows=[]; last_signal=None
    ev=events[(events.signal_time>=start)&(events.signal_time<end)].sort_values("signal_time")
    for e in ev.itertuples(index=False):
        t=pd.Timestamp(e.signal_time)
        # Full max-hold horizon must fit inside the evaluation window.
        if t+pd.Timedelta(hours=8)>end: continue
        if last_signal is not None and t-last_signal<COOLDOWN: continue
        i=int(idx.searchsorted(t))
        if i>=len(idx) or idx[i]!=t: continue
        if i+MAX_HOLD_BARS>len(idx) or not np.all(seg[i:i+MAX_HOLD_BARS]==seg[i]): continue
        if t not in atr15.index or not np.isfinite(atr15.loc[t]) or atr15.loc[t]<=0: continue
        entry=float(op[i]); risk=INITIAL_STOP_ATR15*float(atr15.loc[t])
        if entry<=0 or risk<=0 or risk/entry>0.05: continue
        side=e.side; direction=1 if side=="long" else -1
        stop=entry-direction*risk; target=entry+direction*TARGET_R*risk
        exitp=float(cl[i+MAX_HOLD_BARS-1]); exiti=i+MAX_HOLD_BARS-1; reason="TIME"; ambiguous=False
        for j in range(i,i+MAX_HOLD_BARS):
            fill,why,amb=resolve_bar(side,float(op[j]),float(hi[j]),float(lo[j]),stop,target)
            if why:
                exitp=float(fill); exiti=j; reason=why; ambiguous=ambiguous or amb; break
        gross_r=direction*(exitp-entry)/risk
        gross_pct=direction*(exitp/entry-1.0)*100.0
        held=(exiti-i+1)*5.0/60.0
        row={"period":label,"signal_time":t,"entry_time":idx[i],"exit_time":idx[exiti],
            "side":side,"regime":e.regime,"entry":entry,"initial_stop":stop,
            "target":target,"exit":exitp,"outcome":reason,"gross_R":gross_r,
            "gross_return_pct":gross_pct,"hold_hours":held,"ambiguous_bar":ambiguous,
            "oi_pct":float(e.oi_pct),"oi_z":float(e.oi_z),"price_1h_pct":float(e.price_1h)*100.0,
            "q90_abs_price_1h_pct":float(e.q90_abs_price_1h)*100.0,
            "oi_spike":bool(e.oi_spike)}
        for bps in COSTS_BPS:
            cost_r=(bps/10000.0)/(risk/entry)
            row[f"net_R_{bps}bp"]=gross_r-cost_r
            row[f"net_return_pct_{bps}bp"]=gross_pct-bps/100.0
        rows.append(row); last_signal=t
    return pd.DataFrame(rows)

def metrics(trades: pd.DataFrame, bps: int, period_start: pd.Timestamp,
            period_end: pd.Timestamp) -> dict:
    if trades.empty:
        return {"trades":0,"win_rate_pct":None,"profit_factor":None,"net_R":0.0,
            "avg_R":None,"max_drawdown_R":0.0,"max_losing_streak":0,
            "ambiguous_bars":0,"positive_month_fraction":None,"exposure_pct":0.0}
    x=trades.sort_values("entry_time"); r=x[f"net_R_{bps}bp"].to_numpy(float)
    wins=r[r>0]; losses=r[r<0]; eq=np.cumsum(r)
    dd=eq-np.maximum.accumulate(np.r_[0.0,eq])[1:]
    streak=mx=0
    for v in r:
        streak=streak+1 if v<0 else 0; mx=max(mx,streak)
    monthly=x.assign(month=x.exit_time.dt.strftime("%Y-%m")).groupby("month")[f"net_R_{bps}bp"].sum()
    exposure=float(x.hold_hours.sum()/max(1.0,(period_end-period_start).total_seconds()/3600.0)*100)
    out={"trades":int(len(x)),"win_rate_pct":round(float((r>0).mean()*100),2),
        "profit_factor":round(float(wins.sum()/abs(losses.sum())),3) if len(losses) and abs(losses.sum())>0 else None,
        "net_R":round(float(r.sum()),3),"avg_R":round(float(r.mean()),4),
        "max_drawdown_R":round(float(min(0.0,dd.min())),3),"max_losing_streak":int(mx),
        "ambiguous_bars":int(x.ambiguous_bar.sum()),
        "positive_month_fraction":round(float((monthly>0).mean()),3) if len(monthly) else None,
        "months_with_trades":int(len(monthly)),"exposure_pct":round(exposure,3),
        "tp":int((x.outcome=="TP").sum()),"sl":int((x.outcome=="SL").sum()),
        "time":int((x.outcome=="TIME").sum())}
    # Circular moving-block bootstrap of trade-level expectancy; descriptive only.
    if len(r)>=20:
        rng=np.random.default_rng(20261115); block=4; reps=[]
        for _ in range(2000):
            sample=[]
            while len(sample)<len(r):
                start=int(rng.integers(0,len(r)))
                sample.extend(r[(start+np.arange(block))%len(r)].tolist())
            reps.append(float(np.mean(sample[:len(r)])))
        out["mean_R_block_bootstrap_95ci"]=[round(float(v),4) for v in np.quantile(reps,[.025,.975])]
    else:
        out["mean_R_block_bootstrap_95ci"]=None
    return out

def evaluate_all(events,bars5,atr15,periods):
    all_trades=[]; report={}
    period_specs=[periods["initial_train"]]+periods["validation_folds"]+[periods["final_holdout"]]
    for spec in period_specs:
        t=simulate_period(events,bars5,atr15,spec["start"],spec["end"],spec["name"])
        if not t.empty: all_trades.append(t)
        report[spec["name"]]={"start":spec["start"].isoformat(),"end":spec["end"].isoformat(),
            "costs":{str(b):metrics(t,b,spec["start"],spec["end"]) for b in COSTS_BPS}}
    for fold in periods["validation_folds"]:
        train=simulate_period(events,bars5,atr15,fold["train_start"],fold["train_end"],fold["name"]+"_expanding_train")
        report[fold["name"]]["expanding_train_12bp"]=metrics(train,12,fold["train_start"],fold["train_end"])
    trades=pd.concat(all_trades,ignore_index=True) if all_trades else pd.DataFrame()
    return trades,report

def self_test():
    # Stop-first ambiguity and adverse stop-gap execution.
    assert resolve_bar("long",100,112,88,90,110)==(90.0,"SL",True)
    assert resolve_bar("short",100,112,88,110,90)==(110.0,"SL",True)
    assert resolve_bar("long",85,95,80,90,110)==(85.0,"SL",False)
    assert resolve_bar("short",115,120,112,110,90)==(115.0,"SL",False)
    assert resolve_bar("long",115,120,112,90,110)==(110.0,"TP",False)
    # A 5m gap prevents aggregation into a complete 15m candle.
    ix=pd.date_range("2026-01-01",periods=6,freq="5min",tz="UTC").delete(2)
    z=pd.DataFrame({"open":100.0,"high":101.0,"low":99.0,"close":100.0},index=ix)
    resampled=complete_resample(z,"15min",3,BAR5)
    assert len(resampled)==1 and resampled.index[0]==pd.Timestamp("2026-01-01 00:30:00",tz="UTC")
    # OI candle open timestamp becomes available at its close; current return is
    # excluded from the rolling baseline by shift(1).
    hix=pd.date_range("2026-01-01",periods=220,freq="1h",tz="UTC")+BAR1H
    h=pd.DataFrame({"open":100.0,"high":101.0,"low":99.0,
        "close":100.0+np.arange(220)*0.1},index=hix)
    oi=pd.DataFrame({"open":1000.0+np.arange(220),"high":1000.0+np.arange(220)+1,
        "low":1000.0+np.arange(220),"close":1000.0+np.arange(220)},index=hix-BAR1H)
    oi.loc[oi.index[150],"low"]=0.0  # known OI low sentinel; close remains usable
    f=build_hourly_features(h,oi)
    assert f.index.equals(hix)
    assert pd.isna(f.oi_pct.iloc[0])
    # Alter the current close: its prior-only q90 baseline must not change.
    h2=h.copy(); h2.iloc[180,h2.columns.get_loc("close")]*=1.5
    f2=build_hourly_features(h2,oi)
    assert np.isclose(f.q90_abs_price_1h.iloc[180],f2.q90_abs_price_1h.iloc[180],equal_nan=True)
    with tempfile.TemporaryDirectory() as td:
        oi_path=Path(td)/"oi.csv"
        oi.rename_axis("timestamp").reset_index().to_csv(oi_path,index=False)
        loaded=load_ohlc(oi_path,"synthetic OI",allow_zero_low=True)
        assert loaded.low.iloc[150]==0 and loaded.close.iloc[150]>0
        try:
            load_ohlc(oi_path,"synthetic OI strict")
            raise AssertionError("strict OHLC validator should reject zero low")
        except StudyError:
            pass
    p=make_periods(pd.Timestamp("2024-11-15",tz="UTC"),pd.Timestamp("2026-11-15",tz="UTC"))
    assert p["final_holdout"]["start"]==pd.Timestamp("2026-05-15",tz="UTC")
    assert len(p["validation_folds"])==6
    print("8 OI walk-forward causality/execution self-tests passed")

def run(oi_path: Path, price_path: Path, out: Path):
    out.mkdir(parents=True,exist_ok=True)
    oi=load_ohlc(oi_path,"BTC OI 1h",allow_zero_low=True)
    raw=load_ohlc(price_path,"BTC traded 5m")
    if raw.index.to_series().diff().dropna().eq(pd.Timedelta(0)).any():
        raise StudyError("duplicate 5m timestamps")
    bars5=raw.copy(); bars5["segment"]=segment_ids(bars5.index,BAR5).to_numpy()
    bars15=complete_resample(bars5,"15min",3,BAR5)
    bars1h=complete_resample(bars5,"1h",12,BAR5)
    if bars15.empty or bars1h.empty: raise StudyError("insufficient complete 15m/1h bars")
    atr15=wilder_atr(bars15)
    features=build_hourly_features(bars1h,oi)
    events=build_events(features)
    if events.empty: raise StudyError("No OI contraction + price impulse events")
    start=features.index.min(); end=features.index.max()
    periods=make_periods(start,end)
    trades,period_report=evaluate_all(events,bars5,atr15,periods)
    events.to_csv(out/"events.csv",index=False)
    trades.to_csv(out/"trades.csv",index=False)
    monthly=[]
    if not trades.empty:
        for (period,month),g in trades.assign(month=trades.exit_time.dt.strftime("%Y-%m")).groupby(["period","month"]):
            monthly.append({"period":period,"month":month,"trades":len(g),
                "net_R_12bp":round(float(g.net_R_12bp.sum()),4),
                "win_rate_pct":round(float((g.net_R_12bp>0).mean()*100),2)})
    pd.DataFrame(monthly).to_csv(out/"monthly.csv",index=False)
    regimes=[]
    if not trades.empty:
        for (period,regime,side),g in trades.groupby(["period","regime","side"]):
            regimes.append({"period":period,"regime":regime,"side":side,"trades":len(g),
                "net_R_12bp":round(float(g.net_R_12bp.sum()),4),
                "avg_R_12bp":round(float(g.net_R_12bp.mean()),4),
                "win_rate_pct":round(float((g.net_R_12bp>0).mean()*100),2)})
    pd.DataFrame(regimes).to_csv(out/"regime_side.csv",index=False)
    report={"status":"completed","symbol":"BTCUSD","venue":"Delta Exchange India",
        "signal_timeframe":"1h","execution_timeframe":"5m","source_price":"traded-price OHLCV",
        "data":{"price_5m_rows":len(raw),"price_5m_first_open_utc":raw.index.min().isoformat(),
            "price_5m_last_open_utc":raw.index.max().isoformat(),
            "price_5m_gaps":int((raw.index.to_series().diff().dropna()!=BAR5).sum()),
            "price_5m_sha256":sha256_file(price_path),
            "complete_15m_bars":len(bars15),"complete_1h_bars":len(bars1h),
            "oi_1h_rows":len(oi),"oi_1h_first_open_utc":oi.index.min().isoformat(),
            "oi_1h_last_open_utc":oi.index.max().isoformat(),
            "oi_1h_gaps":int((oi.index.to_series().diff().dropna()!=BAR1H).sum()),
            "oi_1h_nonpositive_close_rows":int((oi.close<=0).sum()),
            "oi_1h_zero_low_rows":int((oi.low==0).sum()),
            "oi_abs_change_gt20pct":int((oi.close.where(oi.close>0).pct_change(fill_method=None).abs()>.20).sum()),
            "oi_1h_sha256":sha256_file(oi_path)},
        "definition":{"signal":"completed 1h OI close-to-close change <0 and prior-only 168h z-score <= -1.5; absolute BTC 1h close return >= prior-only 168h 90th percentile",
            "direction":"follow sign of BTC 1h return",
            "entry":"next 5m open at the completed 1h signal close",
            "stop":"1.5 x Wilder ATR(14) of last completed 15m bar",
            "target":"2.0R fixed",
            "max_hold":"8h (96 x 5m bars)","cooldown":"8h from previous accepted signal",
            "risk":"one position at a time; one frozen configuration",
            "costs":"6/12/20 bps round-trip assumptions; 12bp primary",
            "fills":"5m OHLC; stop-first if both stop and target touch; adverse gap-through stop fill; target fills at target",
            "funding":"excluded; raw funding units and settlement semantics not verified"},
        "period_design":{"initial_train":"first 6 calendar months",
            "validation":"expanding-train, consecutive 2-calendar-month validation folds",
            "final_holdout":"last 6 calendar months; evaluated once; no tuning",
            "periods":{k:{"start":v["start"].isoformat(),"end":v["end"].isoformat()}
                for k,v in periods.items() if k!="validation_folds"},
            "validation_folds":[{"name":v["name"],"train_start":v["train_start"].isoformat(),
                "train_end":v["train_end"].isoformat(),"validation_start":v["start"].isoformat(),
                "validation_end":v["end"].isoformat()} for v in periods["validation_folds"]]},
        "period_metrics":period_report,"event_count":int(len(events)),
        "events_with_oi_change_gt20pct":int(events.oi_spike.sum()),
        "total_trades":int(len(trades)),
        "ambiguous_trade_count":int(trades.ambiguous_bar.sum()) if not trades.empty else 0,
        "limitations":["OI change is unit-invariant but the exact Delta OI sampling semantics are not fully proven by the short pilot.",
            "Funding, spread, market impact and exchange fee tier are not included; flat bps costs are assumptions.",
            "5m OHLC still leaves intrabar ambiguity; ambiguous stop/target bars are counted and resolved stop-first.",
            "One preregistered rule is tested; no parameter selection or strategy promotion is performed."]}
    (out/"report.json").write_text(json.dumps(report,indent=2,default=str)+"\n")
    print(json.dumps(report,indent=2,default=str))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--oi-csv",type=Path)
    p.add_argument("--price-5m-csv",type=Path)
    p.add_argument("--output-dir",type=Path,default=Path("results/btc-oi-walkforward"))
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:self_test();return
    if not a.oi_csv or not a.price_5m_csv:p.error("provide --oi-csv and --price-5m-csv")
    run(a.oi_csv,a.price_5m_csv,a.output_dir)

if __name__=="__main__": main()
