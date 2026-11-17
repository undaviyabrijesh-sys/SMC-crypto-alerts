#!/usr/bin/env python3
"""Frozen Binance ETHUSDT cross-exchange replication of the Delta ETH EMA study."""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

BASE="https://fapi.binance.com/fapi/v1/klines"
SYMBOL="ETHUSDT"; INTERVAL="15m"; STEP=pd.Timedelta(minutes=15)
STEP_MS=900_000; LIMIT=1500
DATA_START=pd.Timestamp("2025-03-08T00:00:00Z")
EVAL_START=pd.Timestamp("2025-09-08T12:00:00Z")
EVAL_END=pd.Timestamp("2026-07-15T00:00:00Z")
HORIZONS={"1h":4,"4h":16}; COSTS=(4.,7.,10.,20.); PRIMARY=10.
SEED=20261117; BOOT_REPS=5000

def download(out: Path) -> pd.DataFrame:
    out.mkdir(parents=True,exist_ok=True)
    cache=out/"ETHUSDT_15m_binance.csv"
    if cache.exists():
        d=pd.read_csv(cache,parse_dates=["timestamp"]).set_index("timestamp").sort_index()
        return d
    start=int(DATA_START.timestamp()*1000); end=int(EVAL_END.timestamp()*1000)
    sess=requests.Session(); rows=[]; cursor=start; calls=0
    while cursor<end:
        stop=min(cursor+LIMIT*STEP_MS-1,end-1)
        params={"symbol":SYMBOL,"interval":INTERVAL,"startTime":cursor,"endTime":stop,"limit":LIMIT}
        last_error=None
        for attempt in range(6):
            try:
                r=sess.get(BASE,params=params,timeout=30)
                if r.status_code in (418,429):
                    time.sleep(min(2**attempt,30)); continue
                r.raise_for_status(); payload=r.json()
                if not isinstance(payload,list): raise RuntimeError(f"Unexpected Binance response: {payload}")
                last_error=None; break
            except Exception as exc:
                last_error=exc; time.sleep(min(2**attempt,20))
        if last_error is not None: raise RuntimeError(f"Download failed at {cursor}: {last_error}")
        if not payload: break
        rows.extend(payload); calls+=1
        last=int(payload[-1][0]); nxt=last+STEP_MS
        if nxt<=cursor: raise RuntimeError("Binance pagination did not advance")
        cursor=nxt
        time.sleep(0.08)
    if not rows: raise RuntimeError("No Binance klines returned")
    d=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"])
    d["timestamp"]=pd.to_datetime(d.open_time.astype("int64"),unit="ms",utc=True)
    d=d[["timestamp","open","high","low","close","volume"]].copy().set_index("timestamp")
    for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d[~d.index.duplicated(keep="last")].sort_index()
    d.to_csv(cache)
    (out/"download_metadata.json").write_text(json.dumps({"venue":"Binance USDⓈ-M","symbol":SYMBOL,"interval":INTERVAL,"start":str(d.index.min()),"end_open":str(d.index.max()),"rows":len(d),"requests":calls},indent=2))
    return d

def rma(x: pd.Series,n:int)->pd.Series:
    a=x.to_numpy(float); out=np.full(len(a),np.nan)
    if len(a)<n or not np.isfinite(a[:n]).all(): return pd.Series(out,index=x.index)
    out[n-1]=float(a[:n].mean())
    for i in range(n,len(a)):
        if np.isfinite(a[i]): out[i]=(out[i-1]*(n-1)+a[i])/n
    return pd.Series(out,index=x.index)

def load_source(path:Path)->pd.DataFrame:
    d=pd.read_csv(path,parse_dates=["timestamp"]).set_index("timestamp").sort_index()
    if d.index.tz is None: d.index=d.index.tz_localize("UTC")
    else: d.index=d.index.tz_convert("UTC")
    d=d[~d.index.duplicated(keep="last")].copy()
    cols=["open","high","low","close","volume"]
    for c in cols: d[c]=pd.to_numeric(d[c],errors="coerce")
    ok=np.isfinite(d[cols]).all(axis=1)
    ok &= (d[["open","high","low","close"]]>0).all(axis=1)
    ok &= d.high.ge(d[["open","low","close"]].max(axis=1))
    ok &= d.low.le(d[["open","high","close"]].min(axis=1))
    ok &= d.volume.ge(0)
    d=d.loc[ok].copy()
    d["segment"]=d.index.to_series().diff().ne(STEP).cumsum().astype(int)
    return d

def aggregate_4h(d15):
    out=[]
    for seg,g in d15.groupby("segment",sort=True):
        x=g[["open","high","low","close","volume"]].resample("4h",label="right",closed="left",origin="epoch").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        n=g.close.resample("4h",label="right",closed="left",origin="epoch").count()
        x=x.loc[n.eq(16)].copy()
        if not x.empty: x["segment"]=int(seg); out.append(x)
    if not out: raise RuntimeError("No complete 4h bars")
    return pd.concat(out).sort_index()

def add_features(d15):
    parts=[]
    for seg,g in d15.groupby("segment",sort=True):
        x=g.copy(); prev=x.close.shift(1)
        tr=pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()],axis=1).max(axis=1)
        x["atr14"]=rma(tr,14)
        x["ema20"]=x.close.ewm(span=20,adjust=False,min_periods=20).mean()
        x["prev_close"]=x.close.shift(1); x["prev_ema20"]=x.ema20.shift(1)
        parts.append(x)
    d15=pd.concat(parts).sort_index(); d4=aggregate_4h(d15); q=[]
    for seg,g in d4.groupby("segment",sort=True):
        x=g.copy(); x["ema50"]=x.close.ewm(span=50,adjust=False,min_periods=50).mean()
        x["ema200"]=x.close.ewm(span=200,adjust=False,min_periods=200).mean()
        x["regime"]=np.where((x.close>x.ema50)&(x.ema50>x.ema200),"bull",np.where((x.close<x.ema50)&(x.ema50<x.ema200),"bear","neutral"))
        q.append(x)
    d4=pd.concat(q).sort_index()
    ctx=d4[["close","ema50","ema200","regime","segment"]].rename(columns={"close":"ctx_close","segment":"ctx_segment"}).reset_index(names="ctx_time").sort_values("ctx_time")
    sig=d15.reset_index(names="signal_open").sort_values("signal_open")
    sig["signal_time"]=sig.signal_open+STEP
    sig=sig.sort_values("signal_time")
    sig=pd.merge_asof(sig,ctx,left_on="signal_time",right_on="ctx_time",direction="backward",allow_exact_matches=True)
    sig=sig[sig.segment.eq(sig.ctx_segment)].copy().set_index("signal_time").sort_index()
    return d4,sig

def next_settlement(ts):
    day=ts.normalize()
    return next(x for x in [day,day+pd.Timedelta(hours=8),day+pd.Timedelta(hours=16),day+pd.Timedelta(days=1)] if x>ts)

def classify(r):
    vals=[r.atr14,r.ema20,r.prev_ema20,r.prev_close,r.ema50,r.ema200,r.ctx_close]
    if not np.isfinite(vals): return None
    if r.regime=="bull" and r.prev_close<=r.prev_ema20 and abs(r.low-r.ema20)<=.10*r.atr14 and r.close>r.ema20 and r.close>r.open: return "long"
    if r.regime=="bear" and r.prev_close>=r.prev_ema20 and abs(r.high-r.ema20)<=.10*r.atr14 and r.close<r.ema20 and r.close<r.open: return "short"
    return None

def build_events(d15,sig):
    rows=[]; last=None; idx=d15.index
    for ts,r in sig.iterrows():
        if ts<EVAL_START or ts>=EVAL_END: continue
        side=classify(r)
        if side is None or (last is not None and ts-last<pd.Timedelta(hours=8)): continue
        i=int(idx.searchsorted(ts,side="left"))
        if i>=len(idx) or idx[i]!=ts or int(d15.segment.iloc[i])!=int(r.segment): continue
        if ts+pd.Timedelta(hours=4)>=next_settlement(ts): continue
        j=i+15
        if j>=len(idx) or d15.segment.iloc[i:j+1].nunique()!=1: continue
        rows.append({"event_id":len(rows),"signal_time":ts,"entry_time":ts,"day":ts.strftime("%Y-%m-%d"),"side":side,"side_sign":1 if side=="long" else -1,"regime":r.regime,"utc_bucket_3h":int(ts.hour//3),"entry":float(d15.open.iloc[i])})
        last=ts
    return pd.DataFrame(rows)

def build_controls(d15,sig,events):
    if events.empty: return pd.DataFrame()
    idx=d15.index
    raw=pd.DatetimeIndex([ts for ts,r in sig.iterrows() if EVAL_START<=ts<EVAL_END and classify(r) is not None]).sort_values()
    cand=[]
    for ts,r in sig.iterrows():
        if ts<EVAL_START or ts>=EVAL_END or classify(r) is not None: continue
        if not np.isfinite([r.ema50,r.ema200,r.ctx_close]).all() or r.regime not in ("bull","bear"): continue
        i=int(idx.searchsorted(ts,side="left"))
        if i>=len(idx) or idx[i]!=ts or int(d15.segment.iloc[i])!=int(r.segment): continue
        if ts+pd.Timedelta(hours=4)>=next_settlement(ts): continue
        j=i+15
        if j>=len(idx) or d15.segment.iloc[i:j+1].nunique()!=1: continue
        if len(raw) and np.min(np.abs((raw-ts).total_seconds()))<=3600: continue
        cand.append({"control_time":ts,"entry_time":ts,"day":ts.strftime("%Y-%m-%d"),"regime":r.regime,"utc_bucket_3h":int(ts.hour//3),"entry":float(d15.open.iloc[i])})
    cdf=pd.DataFrame(cand)
    if cdf.empty: return cdf
    rng=np.random.default_rng(SEED); used=set(); out=[]
    for e in events.to_dict("records"):
        pool=cdf[(cdf.day==e["day"])&(cdf.regime==e["regime"])&(cdf.utc_bucket_3h==e["utc_bucket_3h"])&(~cdf.control_time.isin(used))]
        if pool.empty: continue
        pick=pool.iloc[int(rng.integers(0,len(pool)))]; used.add(pick.control_time)
        out.append({"event_id":int(e["event_id"]),"control_time":pick.control_time,"entry_time":pick.entry_time,"day":pick.day,"side":e["side"],"side_sign":int(e["side_sign"]),"regime":e["regime"],"utc_bucket_3h":e["utc_bucket_3h"],"entry":float(pick.entry)})
    return pd.DataFrame(out)

def evaluate(d15,rows):
    if rows.empty: return pd.DataFrame()
    idx=d15.index; out=[]
    for item in rows.to_dict("records"):
        t=pd.Timestamp(item["entry_time"]); i=int(idx.searchsorted(t,side="left"))
        if i>=len(idx) or idx[i]!=t: continue
        for h,n in HORIZONS.items():
            j=i+n-1
            if j>=len(idx) or d15.segment.iloc[i:j+1].nunique()!=1: continue
            px=float(d15.close.iloc[j]); gross=(px/float(item["entry"])-1)*int(item["side_sign"])*10000
            z={**item,"horizon":h,"exit_time":idx[j]+STEP,"exit":px,"gross_bps":gross}
            for b in COSTS: z[f"net_{int(b)}bps"]=gross-b
            out.append(z)
    return pd.DataFrame(out)

def bootstrap_ci(paired,col,reps=BOOT_REPS):
    if paired.empty or paired.day.nunique()<10: return {"lower":None,"upper":None,"clusters":int(paired.day.nunique()) if len(paired) else 0}
    daily=paired.groupby("day")[col].mean().to_numpy(float); rng=np.random.default_rng(SEED+len(daily)); n=len(daily)
    sims=np.empty(reps)
    for k in range(reps): sims[k]=rng.choice(daily,size=n,replace=True).mean()
    lo,hi=np.quantile(sims,[.025,.975])
    return {"lower":float(lo),"upper":float(hi),"clusters":int(n)}

def drawdown(x):
    a=np.asarray(x,float); eq=np.cumsum(a); peak=np.maximum.accumulate(np.r_[0.,eq])[1:]
    return float(np.min(eq-peak)) if len(a) else 0.

def losing_streak(x):
    cur=mx=0
    for v in x: cur=cur+1 if v<0 else 0; mx=max(mx,cur)
    return int(mx)

def self_tests():
    idx=pd.date_range("2025-01-01",periods=16*24,freq="15min",tz="UTC")
    x=pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"volume":1.},index=idx); x["segment"]=1
    d4=aggregate_4h(x); assert len(d4)==len(x)//16
    _,s=add_features(x); changed=x.copy(); changed.iloc[-8:,changed.columns.get_loc("close")]*=1.5
    _,s2=add_features(changed); cut=idx[-8]+STEP; prior=s.index[s.index<cut]
    assert np.allclose(s.loc[prior,"ema20"],s2.loc[prior,"ema20"],equal_nan=True)
    assert next_settlement(pd.Timestamp("2026-11-17T07:59:00Z"))==pd.Timestamp("2026-11-17T08:00:00Z")
    assert next_settlement(pd.Timestamp("2026-11-17T08:00:00Z"))==pd.Timestamp("2026-11-17T16:00:00Z")
    return ["complete_4h_aggregation","future_perturbation_invariance","funding_settlement_grid"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",default="binance_eth_ema_results"); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    tests=self_tests()
    if a.self_test:
        print("\n".join("PASS "+x for x in tests)); return
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    raw=download(out); raw.to_csv(out/"source_raw.csv")
    d=load_source(out/"source_raw.csv")
    gaps=int((d.index.to_series().diff().dropna()!=STEP).sum())
    digest=hashlib.sha256(out.joinpath("source_raw.csv").read_bytes()).hexdigest()
    d4,sig=add_features(d); events=build_events(d,sig); controls=build_controls(d,sig,events)
    er=evaluate(d,events); cr=evaluate(d,controls)
    events.to_csv(out/"events.csv",index=False); controls.to_csv(out/"controls.csv",index=False); er.to_csv(out/"event_returns.csv",index=False); cr.to_csv(out/"control_returns.csv",index=False)
    folds=[]; cur=EVAL_START
    while cur<EVAL_END:
        nxt=min(cur+pd.DateOffset(months=2),EVAL_END); folds.append((cur,nxt)); cur=nxt
    summary={}; monthly=[]; wf=[]; sides=[]; costs=[]
    for h in HORIZONS:
        e=er[er.horizon==h]; c=cr[cr.horizon==h]
        p=e.merge(c[["event_id","net_10bps","gross_bps"]].rename(columns={"net_10bps":"control_net_10bps","gross_bps":"control_gross_bps"}),on="event_id",how="inner")
        if p.empty: summary[h]={"events":len(e),"matched":0}; continue
        x=p.net_10bps.to_numpy(float); pos=x[x>0].sum(); neg=-x[x<0].sum(); lift=x-p.control_net_10bps.to_numpy(float)
        order=p.sort_values("entry_time")
        mon=p.assign(month=pd.to_datetime(p.entry_time,utc=True).dt.strftime("%Y-%m")).groupby("month").net_10bps.mean()
        for m,v in mon.items(): monthly.append({"horizon":h,"month":m,"matched":int((pd.to_datetime(p.entry_time,utc=True).dt.strftime("%Y-%m")==m).sum()),"event_mean_net10_bps":float(v)})
        fold_means=[]
        for lo,hi in folds:
            q=p[(p.entry_time>=lo)&(p.entry_time<hi)]
            wf.append({"horizon":h,"fold":f"{lo.date()}..{hi.date()}","events":len(q),"event_mean_net10_bps":float(q.net_10bps.mean()) if len(q) else None,"paired_lift_bps":float((q.net_10bps-q.control_net_10bps).mean()) if len(q) else None})
            if len(q): fold_means.append(float(q.net_10bps.mean()))
        summary[h]={"events":len(e),"matched":len(p),"match_rate":len(p)/len(e) if len(e) else None,
            "win_rate_net10":float((x>0).mean()),"descriptive_pf_net10":float(pos/neg) if neg else None,
            "event_mean_gross_bps":float(p.gross_bps.mean()),"event_mean_net10_bps":float(x.mean()),"event_median_net10_bps":float(np.median(x)),
            "control_mean_net10_bps":float(p.control_net_10bps.mean()),"paired_lift_bps":float(lift.mean()),
            "event_mean_day_cluster_ci":bootstrap_ci(p,"net_10bps"),"paired_lift_day_cluster_ci":bootstrap_ci(p.assign(lift=lift),"lift"),
            "event_sequence_drawdown_bps":drawdown(order.net_10bps),"max_losing_streak":losing_streak(order.net_10bps),
            "positive_months":int((mon>0).sum()),"active_months":len(mon),"positive_fold_fraction":float(np.mean(np.asarray(fold_means)>0)) if fold_means else None}
        for side,reg,g in p.groupby(["side","regime"]):
            sides.append({"horizon":h,"side":side,"regime":reg,"matched":len(g),"win_rate":float((g.net_10bps>0).mean()),"mean_net10_bps":float(g.net_10bps.mean()),"paired_lift_bps":float((g.net_10bps-g.control_net_10bps).mean())})
        for b in COSTS:
            costs.append({"horizon":h,"cost_bps":b,"events":len(p),"event_mean_net_bps":float((p.gross_bps-b).mean()),"control_mean_net_bps":float((p.control_gross_bps-b).mean()),"paired_lift_bps":float(lift.mean())})
    pd.DataFrame(monthly).to_csv(out/"monthly_results.csv",index=False); pd.DataFrame(wf).to_csv(out/"walk_forward_folds.csv",index=False); pd.DataFrame(sides).to_csv(out/"side_regime_breakdown.csv",index=False); pd.DataFrame(costs).to_csv(out/"cost_sensitivity.csv",index=False)
    meta={"venue":"Binance USDⓈ-M","symbol":SYMBOL,"interval":INTERVAL,"rows":len(d),"start":str(d.index.min()),"end_open":str(d.index.max()),"duplicates_removed":int(len(raw)-len(d)),"missing_15m_intervals":gaps,"malformed_rows_removed":int(len(raw)-len(d)),"zero_volume_rows":int((d.volume==0).sum()),"complete_4h_bars":len(d4),"source_sha256":digest,"evaluation_start":str(EVAL_START),"evaluation_end_exclusive":str(EVAL_END),"oos":"not downloaded or evaluated","self_tests":tests,"events":len(events),"matched_controls":len(controls),"summary":summary}
    (out/"summary.json").write_text(json.dumps(meta,indent=2,default=str))
    report=["# Binance ETHUSDT 15m EMA20 cross-exchange replication","",f"- Source rows: {len(d):,}; missing 15m intervals: {gaps}; complete 4h bars: {len(d4):,}.",f"- Range: {d.index.min()} to {d.index.max()} (bar open).",f"- Events: {len(events)}; matched controls: {len(controls)}; OOS not downloaded or evaluated.","","## Results at 10 bps round-trip cost",""]
    for h,z in summary.items():
        report += [f"### {h}",f"- Events/matched: {z.get('events')} / {z.get('matched')}",f"- Win rate: {z.get('win_rate_net10')}",f"- PF: {z.get('descriptive_pf_net10')}",f"- Event mean/median: {z.get('event_mean_net10_bps')} / {z.get('event_median_net10_bps')} bps",f"- Control mean: {z.get('control_mean_net10_bps')} bps; paired lift: {z.get('paired_lift_bps')} bps",f"- Event mean CI: {z.get('event_mean_day_cluster_ci')}; lift CI: {z.get('paired_lift_day_cluster_ci')}",f"- Positive months: {z.get('positive_months')}/{z.get('active_months')}; max losing streak: {z.get('max_losing_streak')}",""]
    report += ["R, stop-based PnL and account drawdown are not applicable: this is a fixed-horizon event study without stops or targets.","No parameter search or final holdout evaluation was performed."]
    (out/"REPORT.md").write_text("\n".join(report))
    print(json.dumps(meta,indent=2,default=str))

if __name__=="__main__": main()
