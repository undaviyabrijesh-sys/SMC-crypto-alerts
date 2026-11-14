#!/usr/bin/env python3
"""Preregistered BTC 1h EMA20 pullback event study with completed 4h trend bias.

Input is Delta BTCUSD traded-price 15m OHLCV. Only complete, contiguous 1h
and 4h bars are used. Signal is known at a 1h close; entry is the next 1h open.
The study measures forward returns, not stop/target execution PnL.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR15 = pd.Timedelta(minutes=15)
H1 = pd.Timedelta(hours=1)
H4 = pd.Timedelta(hours=4)
HORIZONS = {"4h": 4, "8h": 8, "24h": 24}
COSTS_BPS = (6.0, 12.0, 20.0)
COOLDOWN_H1 = 8
TOLERANCE_ATR = 0.10
CONTROL_SEED = 20261114
CONTROL_EXCLUSION_H1 = 1
BOOTSTRAP_REPS = 3000
BLOCK_LENGTH = 7
PERIODS = {
    "development": ("2024-11-14T00:00:00Z", "2025-11-14T00:00:00Z"),
    "validation": ("2025-11-14T00:00:00Z", "2026-05-14T00:00:00Z"),
    "final_holdout": ("2026-05-14T00:00:00Z", "2026-11-14T00:00:00Z"),
}

class StudyError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def load_15m(path: Path) -> pd.DataFrame:
    d=pd.read_csv(path)
    if "timestamp" not in d: raise StudyError("CSV missing timestamp")
    d["timestamp"]=pd.to_datetime(d.timestamp,utc=True,errors="raise")
    if d.timestamp.duplicated().any(): raise StudyError("duplicate 15m timestamps")
    d=d.sort_values("timestamp").set_index("timestamp")
    if not ((d.index.minute%15==0)&(d.index.second==0)).all():
        raise StudyError("15m timestamps are not aligned to UTC quarter-hours")
    for c in ("open","high","low","close"):
        d[c]=pd.to_numeric(d[c],errors="raise")
    if "volume" not in d: d["volume"]=0.0
    d["volume"]=pd.to_numeric(d.volume,errors="raise")
    a=d[["open","high","low","close","volume"]].to_numpy(float)
    if not np.isfinite(a).all(): raise StudyError("non-finite OHLCV")
    if (d[["open","high","low","close"]]<=0).any().any(): raise StudyError("non-positive OHLC")
    if (d.volume<0).any(): raise StudyError("negative volume")
    bad=(d.high<d[["open","close","low"]].max(axis=1))|(d.low>d[["open","close","high"]].min(axis=1))
    if bad.any(): raise StudyError(f"invalid OHLC rows={int(bad.sum())}")
    d["segment"]=(d.index.to_series().diff().ne(BAR15)).cumsum().astype(int)
    return d

def complete_resample(d: pd.DataFrame, rule: str, expected: int, step: pd.Timedelta) -> pd.DataFrame:
    # Right label: the bar timestamp is its close; only closed complete groups survive.
    kw={"label":"right","closed":"left"}
    z=d[["open","high","low","close","volume"]].resample(rule,**kw).agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
    counts=d.close.resample(rule,**kw).count()
    segs=d.segment.resample(rule,**kw).nunique()
    z=z.loc[counts.eq(expected)&segs.eq(1)].dropna(subset=["open","high","low","close"])
    # Reject partial/misaligned groups even if count happens to match.
    z["segment"]=(z.index.to_series().diff().ne(step)).cumsum().astype(int)
    return z

def add_segmented_ema(s: pd.Series, segment: pd.Series, span: int, min_periods: int|None=None) -> pd.Series:
    mp=span if min_periods is None else min_periods
    return s.groupby(segment,sort=False).transform(
        lambda x:x.ewm(span=span,adjust=False,min_periods=mp).mean())

def add_segmented_atr(h1: pd.DataFrame) -> pd.Series:
    out=pd.Series(np.nan,index=h1.index,dtype=float)
    for _,g in h1.groupby("segment",sort=False):
        prev=g.close.shift(1)
        tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
        out.loc[g.index]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    return out

def align_completed_regime(h1_index: pd.DatetimeIndex, h4: pd.DataFrame) -> pd.Series:
    regime=h4.regime.reindex(h1_index,method="ffill")
    last=h4.index.to_series().reindex(h1_index,method="ffill")
    age=pd.Series(h1_index,index=h1_index)-last
    return regime.where(age<H4,"unavailable").fillna("unavailable")

def completed_4h_regime(h1: pd.DataFrame, h4: pd.DataFrame) -> pd.Series:
    h=h4.copy()
    h["ema50"]=add_segmented_ema(h.close,h.segment,50)
    h["ema200"]=add_segmented_ema(h.close,h.segment,200)
    bull=(h.close>h.ema50)&(h.ema50>h.ema200)
    bear=(h.close<h.ema50)&(h.ema50<h.ema200)
    h["regime"]=np.select([bull,bear],["bull","bear"],default="neutral")
    # A completed 4h bar is usable at its right-labelled close, never earlier.
    return align_completed_regime(h1.index,h)

def prepare(path: Path) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    raw=load_15m(path)
    h1=complete_resample(raw,"1h",4,H1)
    h4=complete_resample(raw,"4h",16,H4)
    if h1.empty or h4.empty: raise StudyError("insufficient complete 1h/4h candles")
    h1["ema20"]=add_segmented_ema(h1.close,h1.segment,20)
    h1["atr14"]=add_segmented_atr(h1)
    h1["regime4h"]=completed_4h_regime(h1,h4)
    gaps=int((raw.index.to_series().diff()>BAR15*1.5).sum())
    meta={"rows_15m":int(len(raw)),"rows_1h":int(len(h1)),"rows_4h":int(len(h4)),
          "first_15m_utc":raw.index.min().isoformat(),"last_15m_open_utc":raw.index.max().isoformat(),
          "gap_count_15m":gaps,"irregular_intervals_15m":int((raw.index.to_series().diff().dropna()!=BAR15).sum()),
          "csv_sha256":sha256_file(path)}
    return raw,h1,meta

def build_events(h1: pd.DataFrame) -> pd.DataFrame:
    rows=[]; last_signal=-10**9
    for i in range(1,len(h1)-1):
        if i-last_signal<COOLDOWN_H1: continue
        if h1.segment.iloc[i-1]!=h1.segment.iloc[i] or h1.segment.iloc[i]!=h1.segment.iloc[i+1]:
            continue
        prev_close=float(h1.close.iloc[i-1]); prev_ema=float(h1.ema20.iloc[i-1])
        ema=float(h1.ema20.iloc[i]); atr=float(h1.atr14.iloc[i])
        o=float(h1.open.iloc[i]); hi=float(h1.high.iloc[i]); lo=float(h1.low.iloc[i]); c=float(h1.close.iloc[i])
        regime=str(h1.regime4h.iloc[i])
        if not np.isfinite([prev_close,prev_ema,ema,atr]).all() or atr<=0:
            continue
        side=None
        # Signal candle is complete at h1.index[i]. Entry is next 1h candle open.
        if regime=="bull" and prev_close<=prev_ema and abs(lo-ema)<=TOLERANCE_ATR*atr and c>ema and c>o:
            side="long"
        elif regime=="bear" and prev_close>=prev_ema and abs(hi-ema)<=TOLERANCE_ATR*atr and c<ema and c<o:
            side="short"
        if side is None: continue
        entry_i=i+1
        if entry_i+max(HORIZONS.values())-1>=len(h1): continue
        if h1.segment.iloc[entry_i:entry_i+max(HORIZONS.values())].nunique()!=1: continue
        side_sign=1 if side=="long" else -1
        rows.append({"event_id":len(rows),"signal_i":int(i),"entry_i":int(entry_i),
          "signal_time":h1.index[i].isoformat(),"entry_time":h1.index[i].isoformat(),
          "day":str(h1.index[i].date()),"utc_3h_bucket":int(h1.index[i].hour//3),
          "side":side,"side_sign":side_sign,"htf_regime":regime,
          "entry":float(h1.open.iloc[entry_i]),"signal_ema20":ema,"signal_atr14":atr})
        last_signal=i
    return pd.DataFrame(rows)

def build_controls(h1: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if events.empty: return pd.DataFrame()
    rng=np.random.default_rng(CONTROL_SEED)
    event_indices=set(int(x) for x in events.signal_i)
    used=set(); rows=[]
    for e in events.to_dict("records"):
        day=pd.Timestamp(e["day"],tz="UTC")
        lo=int(h1.index.searchsorted(day,side="left"))
        hi=int(h1.index.searchsorted(day+pd.Timedelta(days=1),side="left"))
        candidates=[]
        for k in range(max(1,lo),min(len(h1)-max(HORIZONS.values()),hi)):
            if k in event_indices or k in used: continue
            if abs(k-int(e["signal_i"]))<=CONTROL_EXCLUSION_H1: continue
            if int(h1.index[k].hour//3)!=int(e["utc_3h_bucket"]): continue
            if str(h1.regime4h.iloc[k])!=str(e["htf_regime"]): continue
            if h1.segment.iloc[k-1]!=h1.segment.iloc[k] or h1.segment.iloc[k]!=h1.segment.iloc[k+1]:
                continue
            if h1.segment.iloc[k+1:k+max(HORIZONS.values())+1].nunique()!=1: continue
            candidates.append(k)
        if not candidates: continue
        k=int(rng.choice(candidates)); used.add(k); entry_i=k+1
        rows.append({"event_id":int(e["event_id"]),"signal_i":k,"entry_i":entry_i,
          "control_signal_time":h1.index[k].isoformat(),"control_entry_time":h1.index[k].isoformat(),
          "day":e["day"],"utc_3h_bucket":int(e["utc_3h_bucket"]),
          "side":e["side"],"side_sign":int(e["side_sign"]),"htf_regime":e["htf_regime"],
          "entry":float(h1.open.iloc[entry_i])})
    return pd.DataFrame(rows)

def outcome(h1: pd.DataFrame, signal_i: int, entry_i: int, entry: float,
            side_sign: int, bars: int, period_end: pd.Timestamp) -> dict|None:
    exit_i=signal_i+bars
    if exit_i>=len(h1): return None
    if h1.index[exit_i]>period_end: return None
    if h1.segment.iloc[entry_i:exit_i+1].nunique()!=1: return None
    exit_px=float(h1.close.iloc[exit_i])
    gross=(exit_px/entry-1.0)*side_sign*100.0
    return {"exit_time":h1.index[exit_i].isoformat(),"exit":exit_px,"gross_return_pct":gross}

def evaluate_period(h1: pd.DataFrame, events: pd.DataFrame, controls: pd.DataFrame,
                    period_name: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame,pd.DataFrame]:
    eout=[]; cout=[]
    if events.empty: return pd.DataFrame(),pd.DataFrame()
    matched_ids=set(controls.event_id.astype(int)) if not controls.empty else set()
    ev=events[(pd.to_datetime(events.signal_time,utc=True)>=start)&
              (pd.to_datetime(events.signal_time,utc=True)<end)&events.event_id.isin(matched_ids)]
    for e in ev.to_dict("records"):
        for label,bars in HORIZONS.items():
            r=outcome(h1,int(e["signal_i"]),int(e["entry_i"]),float(e["entry"]),
                      int(e["side_sign"]),bars,end)
            if r is None: continue
            row={**e,"period":period_name,"horizon":label,**r}
            for bps in COSTS_BPS: row[f"net_{int(bps)}bps_pct"]=r["gross_return_pct"]-bps/100.0
            eout.append(row)
        c=controls[controls.event_id.astype(int)==int(e["event_id"])]
        if c.empty: continue
        cr=c.iloc[0].to_dict()
        for label,bars in HORIZONS.items():
            r=outcome(h1,int(cr["signal_i"]),int(cr["entry_i"]),float(cr["entry"]),
                      int(cr["side_sign"]),bars,end)
            if r is None: continue
            row={**cr,"period":period_name,"horizon":label,**r}
            for bps in COSTS_BPS: row[f"net_{int(bps)}bps_pct"]=r["gross_return_pct"]-bps/100.0
            cout.append(row)
    return pd.DataFrame(eout),pd.DataFrame(cout)

def trade_stats(g: pd.DataFrame, cost_col: str) -> dict:
    if g.empty: return {"n":0,"win_rate_pct":None,"profit_factor":None,"mean_net_pct":None,
      "median_net_pct":None,"event_sequence_drawdown_pct":None,"max_losing_streak":0,
      "positive_month_fraction":None}
    z=g.sort_values("entry_time"); r=z[cost_col].astype(float)
    wins=r[r>0]; losses=r[r<0]
    eq=r.cumsum().to_numpy(); peak=np.maximum.accumulate(np.r_[0.0,eq])[1:]
    dd=eq-peak; streak=best=0
    for v in r.to_numpy():
        streak=streak+1 if v<0 else 0; best=max(best,streak)
    monthly=z.assign(month=pd.to_datetime(z.entry_time,utc=True).dt.strftime("%Y-%m")).groupby("month")[cost_col].mean()
    return {"n":int(len(z)),"win_rate_pct":round(float((r>0).mean()*100),2),
      "profit_factor":round(float(wins.sum()/abs(losses.sum())),3) if len(losses) and abs(losses.sum())>0 else None,
      "mean_net_pct":round(float(r.mean()),5),"median_net_pct":round(float(r.median()),5),
      "event_sequence_drawdown_pct":round(float(min(0.0,dd.min())),5),
      "max_losing_streak":int(best),
      "positive_month_fraction":round(float((monthly>0).mean()),4) if len(monthly) else None}

def block_ci(values: np.ndarray, seed: int) -> list[float]|None:
    x=np.asarray(values,float); x=x[np.isfinite(x)]; n=len(x)
    if n<10: return None
    rng=np.random.default_rng(seed); blocks=int(np.ceil(n/BLOCK_LENGTH))
    starts=rng.integers(0,n,size=(BOOTSTRAP_REPS,blocks))
    ix=(starts[:,:,None]+np.arange(BLOCK_LENGTH)[None,None,:])%n
    sample=x[ix.reshape(BOOTSTRAP_REPS,-1)[:,:n]].mean(axis=1)
    return [round(float(v),6) for v in np.quantile(sample,[.025,.975])]

def summarize(e: pd.DataFrame,c: pd.DataFrame) -> tuple[dict,list[dict]]:
    summary={}; monthly_rows=[]
    if e.empty or c.empty:
        return ({p:{h:{"status":"insufficient_events_or_controls","event_n":0,"control_n":0} for h in HORIZONS} for p in PERIODS}, monthly_rows)
    for period in PERIODS:
        summary[period]={}
        for horizon in HORIZONS:
            a=e[(e.period==period)&(e.horizon==horizon)].copy()
            b=c[(c.period==period)&(c.horizon==horizon)].copy()
            key=f"net_12bps_pct"
            if a.empty or b.empty:
                summary[period][horizon]={"status":"insufficient_matched_observations","event_n":len(a),"control_n":len(b)}
                continue
            pair=a[["event_id",key]].merge(b[["event_id",key]],on="event_id",suffixes=("_event","_control"))
            diff=pair[f"{key}_event"]-pair[f"{key}_control"]
            paired_ids=set(pair.event_id.astype(int))
            ap=a[a.event_id.astype(int).isin(paired_ids)]
            bp=b[b.event_id.astype(int).isin(paired_ids)]
            summary[period][horizon]={
              "event_6bps":trade_stats(ap,"net_6bps_pct"),
              "event_12bps":trade_stats(ap,"net_12bps_pct"),
              "event_20bps":trade_stats(ap,"net_20bps_pct"),
              "control_12bps":trade_stats(bp,"net_12bps_pct"),
              "paired_n":int(len(pair)),
              "mean_lift_12bps_pct":round(float(diff.mean()),5),
              "paired_block_bootstrap_95ci_pct":block_ci(diff.to_numpy(),CONTROL_SEED+len(summary[period])+len(horizon)),
            }
            for (side,regime),g in a.groupby(["side","htf_regime"]):
                monthly_rows.append({"period":period,"horizon":horizon,"side":side,"regime":regime,
                  "n":int(len(g)),"mean_net_12bps_pct":round(float(g.net_12bps_pct.mean()),5),
                  "win_rate_pct":round(float((g.net_12bps_pct>0).mean()*100),2)})
            z=a.assign(month=pd.to_datetime(a.entry_time,utc=True).dt.strftime("%Y-%m"))
            for month,g in z.groupby("month"):
                monthly_rows.append({"period":period,"horizon":horizon,"month":month,
                  "n":int(len(g)),"mean_net_12bps_pct":round(float(g.net_12bps_pct.mean()),5),
                  "win_rate_pct":round(float((g.net_12bps_pct>0).mean()*100),2)})
    return summary,monthly_rows

def run(data_csv: Path, out: Path) -> dict:
    raw,h1,meta=prepare(data_csv)
    events=build_events(h1)
    controls=build_controls(h1,events)
    out.mkdir(parents=True,exist_ok=True)
    events.to_csv(out/"events.csv",index=False)
    controls.to_csv(out/"matched_controls.csv",index=False)
    period_events=[]; period_controls=[]
    for name,(a,b) in PERIODS.items():
        e,c=evaluate_period(h1,events,controls,name,pd.Timestamp(a),pd.Timestamp(b))
        period_events.append(e); period_controls.append(c)
    ev=pd.concat(period_events,ignore_index=True) if period_events else pd.DataFrame()
    co=pd.concat(period_controls,ignore_index=True) if period_controls else pd.DataFrame()
    ev.to_csv(out/"event_forward_returns.csv",index=False)
    co.to_csv(out/"control_forward_returns.csv",index=False)
    summary,monthly=summarize(ev,co)
    match_n=int(controls.event_id.nunique()) if not controls.empty else 0
    report={"status":"completed","symbol":"BTCUSD","source":"Delta Exchange India traded-price 15m OHLCV",
      "timeframe_signal":"1h","data":meta,"complete_1h_bars":len(h1),
      "raw_event_count":int(len(events)),"matched_control_count":match_n,
      "match_rate_pct":round(100*match_n/len(events),2) if len(events) else 0.0,
      "long_events":int((events.side=="long").sum()) if not events.empty else 0,
      "short_events":int((events.side=="short").sum()) if not events.empty else 0,
      "definition":{"trend":"completed 4h close > EMA50 > EMA200 for longs; inverse for shorts",
        "entry":"next 1h open after signal 1h close","pullback":"prior 1h close at/beyond EMA20; current 1h low/high within 0.1 ATR14 of EMA20",
        "confirmation":"long close > EMA20 and > open; short close < EMA20 and < open",
        "cooldown_hours":COOLDOWN_H1,"one_event_global_cooldown":True,
        "horizons":HORIZONS,"round_trip_cost_bps_assumptions":COSTS_BPS},
      "periods":summary,"monthly_and_side_regime_diagnostics":monthly,
      "limitations":["event study only; no stop/target, R-multiple or executable portfolio simulation",
        "event-sequence drawdown is not portfolio drawdown; 24h outcomes can overlap because event cooldown is 8h",
        "costs are simple round-trip assumptions; actual fee tier, spread, slippage, funding and impact are not verified",
        "matched controls are observational and do not establish causality",
        "final holdout is reported once and must not be tuned"]}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def self_test():
    idx=pd.date_range("2026-01-01",periods=32,freq="15min",tz="UTC")
    x=pd.DataFrame({"open":np.arange(32)+100.,"high":np.arange(32)+101.,
      "low":np.arange(32)+99.,"close":np.arange(32)+100.5,"volume":1.},
      index=idx)
    x["segment"]=(x.index.to_series().diff().ne(BAR15)).cumsum().astype(int)
    h=complete_resample(x,"1h",4,H1)
    assert len(h)==8 and h.index[0]==idx[0]+H1
    x2=x.drop(idx[5]).copy()
    x2["segment"]=(x2.index.to_series().diff().ne(BAR15)).cumsum().astype(int)
    h2=complete_resample(x2,"1h",4,H1)
    assert len(h2)==7, f"expected seven complete hours around one missing 15m bar, got {len(h2)}"
    # A 4h candle closing at 04:00 cannot influence the 03:00 1h close.
    h1idx=pd.date_range("2026-01-01 01:00",periods=5,freq="1h",tz="UTC")
    h1=pd.DataFrame(index=h1idx)
    h4=pd.DataFrame({"regime":["bull"]},
      index=pd.DatetimeIndex(["2026-01-01 04:00Z"]))
    reg=align_completed_regime(h1.index,h4)
    assert reg.iloc[0]=="unavailable" and reg.iloc[2]=="unavailable"
    assert reg.iloc[3]=="bull" and reg.iloc[4]=="bull"
    # Outcome must use next-bar open and must not cross the fixed period end.
    bars=pd.DataFrame({"open":[100.,101.,102.,103.,104.],
      "high":[101.,102.,103.,104.,105.],"low":[99.,100.,101.,102.,103.],
      "close":[100.5,101.5,102.5,103.5,104.5],"segment":[0,0,0,0,0]},
      index=pd.date_range("2026-01-01 01:00",periods=5,freq="1h",tz="UTC"))
    r=outcome(bars,0,1,101.,1,2,pd.Timestamp("2026-01-01 03:00Z"))
    assert r is not None and abs(r["gross_return_pct"]-(102.5/101.-1)*100)<1e-9
    assert outcome(bars,0,1,101.,1,3,pd.Timestamp("2026-01-01 03:00Z")) is None
    print("PASS complete_resample_alignment")
    print("PASS incomplete_and_gap_bar_rejection")
    print("PASS completed_4h_no_lookahead")
    print("PASS next_open_entry_and_period_boundary")
    print("PASS 4 deterministic tests")\n\n# First CI attempt found only an incorrect expected count in the synthetic gap test;\n# the expected count is corrected and the completed-4h alignment test is isolated.

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-csv",type=Path,default=Path("historical_data/BTC_15m.csv"))
    p.add_argument("--output-dir",type=Path,default=Path("research/results/btc_1h_ema20_pullback"))
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test: self_test(); return
    r=run(a.data_csv,a.output_dir)
    print(json.dumps(r,indent=2))
if __name__=="__main__": main()
