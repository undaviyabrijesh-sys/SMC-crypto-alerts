#!/usr/bin/env python3
"""Preregistered BTC session-range sweep/re-entry forward-return event study.

Research-only. Delta BTCUSD traded-price 5m OHLCV. Asia range: 00:00-06:00 UTC.
Signals: first 06:00-18:00 UTC bar that trades beyond one range edge and closes
back inside. Entry is next 5m open. At most one event per UTC day; if a bar sweeps
both edges it is excluded. No stop/target optimization: measure 15m/1h/4h/8h
forward directional returns. Costs are sensitivity assumptions, not fee claims.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

URL = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL = "BTCUSD"
STEP = pd.Timedelta(minutes=5)
HORIZONS = {"15m": 3, "1h": 12, "4h": 48, "8h": 96}
COSTS_BPS = (6.0, 12.0, 20.0)

class StudyError(RuntimeError): pass

def fetch_data(days: int = 730, delay: float = 0.12) -> pd.DataFrame:
    end = int(pd.Timestamp.now(tz="UTC").floor("5min").timestamp())
    start = end - days * 86400
    span = 300 * 1800 - 1
    rows = []
    session = requests.Session()
    cursor = start
    while cursor < end:
        stop = min(end - 1, cursor + span)
        r = session.get(URL, params={"resolution":"5m","symbol":SYMBOL,
            "start":str(cursor),"end":str(stop)},
            headers={"Accept":"application/json","User-Agent":"SaltyQuantSessionSweep/1.0"},
            timeout=40)
        r.raise_for_status()
        payload = r.json()
        if payload.get("success") is not True:
            raise StudyError(f"Delta API unsuccessful response: {payload}")
        part = payload.get("result") or []
        if len(part) > 1800: raise StudyError("API returned more than 1800 candles")
        rows.extend(part)
        cursor = stop + 1
        time.sleep(delay)
    if not rows: raise StudyError("No BTCUSD candles returned")
    d = pd.DataFrame(rows)
    if not {"time","open","high","low","close"}.issubset(d.columns):
        raise StudyError("Missing OHLC columns")
    d["timestamp"] = pd.to_datetime(pd.to_numeric(d.time,errors="raise"),unit="s",utc=True)
    for c in ("open","high","low","close","volume"):
        if c not in d: d[c] = 0.0
        d[c] = pd.to_numeric(d[c],errors="coerce")
    d = d.drop_duplicates("timestamp",keep="last").sort_values("timestamp").set_index("timestamp")
    vals=d[["open","high","low","close","volume"]].to_numpy(float)
    if not np.isfinite(vals).all(): raise StudyError("Non-finite OHLCV")
    if (d[["open","high","low","close"]]<=0).any().any(): raise StudyError("Non-positive price")
    bad=(d.high<d[["open","close","low"]].max(axis=1))|(d.low>d[["open","close","high"]].min(axis=1))
    if bad.any(): raise StudyError(f"Invalid OHLC rows: {int(bad.sum())}")
    d=d[d.index+STEP<=pd.Timestamp.now(tz="UTC").floor("5min")]
    d["segment"]=(d.index.to_series().diff().ne(STEP)).cumsum().to_numpy()
    return d

def detect_events(d: pd.DataFrame) -> pd.DataFrame:
    x=d.copy()
    x["day"]=x.index.floor("D")
    x["minute"]=x.index.hour*60+x.index.minute
    x["asia"]=x.minute.lt(360)
    x["trade_window"]=x.minute.ge(360)&x.minute.lt(1080)
    rows=[]
    for day,g in x.groupby("day",sort=True):
        asia=g[g.asia]
        if len(asia)<60 or asia.index[-1]-asia.index[0] < pd.Timedelta(hours=4,minutes=55):
            continue
        # Require complete, contiguous Asia session and one data segment.
        if asia.segment.nunique()!=1 or not asia.index.to_series().diff().dropna().eq(STEP).all():
            continue
        rh=float(asia.high.max()); rl=float(asia.low.min())
        win=g[g.trade_window]
        if win.empty: continue
        for ts,row in win.iterrows():
            up=float(row.high)>rh and float(row.close)<rh
            dn=float(row.low)<rl and float(row.close)>rl
            if up and dn: continue
            if up or dn:
                entry_i=d.index.get_indexer([ts])[0]+1
                if entry_i>=len(d): break
                entry_ts=d.index[entry_i]
                if entry_ts-ts!=STEP or d.segment.iloc[entry_i]!=row.segment: break
                side=-1 if up else 1
                rows.append({"signal_time":ts.isoformat(),"entry_time":entry_ts.isoformat(),
                    "day":str(day.date()),"side":"short" if side<0 else "long",
                    "side_sign":side,"range_high":rh,"range_low":rl,
                    "entry":float(d.open.iloc[entry_i]),"sweep_edge":"high" if up else "low"})
                break  # first qualifying event per day; prevents event clustering
    return pd.DataFrame(rows)

def evaluate(d: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame,dict]:
    if events.empty: raise StudyError("No qualifying session sweep events")
    index=d.index
    out=[]
    for e in events.to_dict("records"):
        t=pd.Timestamp(e["entry_time"]); i=index.get_indexer([t])[0]
        for label,bars in HORIZONS.items():
            j=i+bars
            if j>=len(d): continue
            # Do not cross a data gap; horizon close is the close of the final bar.
            if d.segment.iloc[i:j+1].nunique()!=1: continue
            exit_px=float(d.close.iloc[j])
            gross=(exit_px/float(e["entry"])-1.0)*int(e["side_sign"])*100.0
            rec={**e,"horizon":label,"exit_time":index[j].isoformat(),
                 "exit":exit_px,"gross_return_pct":gross}
            for bps in COSTS_BPS:
                rec[f"net_{int(bps)}bps_pct"]=gross-2*bps/100.0
            out.append(rec)
    trades=pd.DataFrame(out)
    if trades.empty: raise StudyError("No complete forward-return observations")
    summary={}
    for horizon,g in trades.groupby("horizon",sort=False):
        net=g["net_12bps_pct"]
        summary[horizon]={"n":int(len(g)),"long_n":int((g.side=="long").sum()),
            "short_n":int((g.side=="short").sum()),
            "mean_gross_pct":round(float(g.gross_return_pct.mean()),5),
            "median_gross_pct":round(float(g.gross_return_pct.median()),5),
            "mean_net_6bps_pct":round(float(g.net_6bps_pct.mean()),5),
            "mean_net_12bps_pct":round(float(net.mean()),5),
            "mean_net_20bps_pct":round(float(g.net_20bps_pct.mean()),5),
            "positive_net_fraction_12bps":round(float((net>0).mean()),4),
            "positive_month_fraction":round(float((g.assign(month=pd.to_datetime(g.entry_time,utc=True).dt.to_period("M"))
                .groupby("month").net_12bps_pct.mean()>0).mean()),4)}
    return trades,summary

def walk_forward(events: pd.DataFrame) -> list[dict]:
    if events.empty: return []
    dates=pd.to_datetime(events.entry_time,utc=True)
    first=dates.min().floor("D"); last=dates.max().floor("D")
    # Frozen calendar folds: 6m warm-up then consecutive 2m evaluation windows.
    cursor=first+pd.DateOffset(months=6); folds=[]
    while cursor<=last:
        end=cursor+pd.DateOffset(months=2)
        g=events[(dates>=cursor)&(dates<end)]
        folds.append({"validation_start":cursor.isoformat(),"validation_end":end.isoformat(),
            "event_count":int(len(g)),
            "long_count":int((g.side=="long").sum()),"short_count":int((g.side=="short").sum())})
        cursor=end
    return folds

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=730)
    p.add_argument("--output-dir",default="research/results/session_sweep")
    a=p.parse_args()
    if a.days<240: raise SystemExit("--days must be at least 240 for the preregistered folds")
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    d=fetch_data(a.days)
    events=detect_events(d)
    trades,summary=evaluate(d,events)
    events.to_csv(out/"events.csv",index=False)
    trades.to_csv(out/"forward_returns.csv",index=False)
    digest=hashlib.sha256(pd.util.hash_pandas_object(d,index=True).values.tobytes()).hexdigest()
    report={"status":"completed","symbol":SYMBOL,"timeframe":"5m","bars":len(d),
      "first_bar_utc":d.index.min().isoformat(),"last_bar_utc":d.index.max().isoformat(),
      "gap_count":int((d.index.to_series().diff()>STEP*1.5).sum()),
      "data_hash_pandas_object_sha256":digest,"event_count":int(len(events)),
      "definition":{"asia_utc":"00:00-06:00","trade_window_utc":"06:00-18:00",
        "entry":"next 5m open","event_limit":"first qualifying event per UTC day",
        "both_edges_same_bar":"excluded","horizons_bars":HORIZONS,
        "cost_sensitivity_round_trip_bps":COSTS_BPS},
      "summary":summary,"walk_forward_event_counts":walk_forward(events),
      "limitations":["5m bars measure signal forward returns, not stop/target execution",
        "costs are simple round-trip sensitivities, not verified Delta fee tier or slippage",
        "events are descriptive and require matched-control/placebo analysis before edge claims"]}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
