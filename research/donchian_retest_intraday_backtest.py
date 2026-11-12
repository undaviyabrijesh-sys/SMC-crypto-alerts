#!/usr/bin/env python3
"""Price-only BTCUSD 15m Donchian breakout-retest backtest."""
from __future__ import annotations
import argparse, hashlib, itertools, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
HOUR = pd.Timedelta(hours=1)
MAX_HOLD = 32
CHANNELS = (20, 40)
BUFFERS = (0.0, 0.1)
TOLERANCES = (0.1, 0.25)
WINDOWS = (4, 8)
CONFIRMS = ("close_hold", "directional_body")
STOPS = ("retest_extreme", "atr1p5")
TARGETS = (1.5, 2.0, 3.0)
FILTERS = ("none", "ema50")
DIRECTIONS = ("both", "long_only", "short_only")
SESSIONS = ("all", "07-19")
VOLUME_FILTERS = ("none", "relvol1p5")
COSTS = (6, 12, 20)
MIN_TRAIN, MIN_VAL, SHORTLIST = 40, 20, 25


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_csv(path):
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d.timestamp = pd.to_datetime(d.timestamp, utc=True)
    if d.timestamp.duplicated().any():
        raise ValueError("duplicate timestamps")
    d = d.sort_values("timestamp").set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="raise")
        if not np.isfinite(d[c].to_numpy(float)).all():
            raise ValueError("non-finite " + c)
    if (d[["open", "high", "low", "close"]] <= 0).any().any() or (d.volume < 0).any():
        raise ValueError("invalid traded-price OHLCV")
    bad = (d.high < d[["open", "close", "low"]].max(axis=1)) | (d.low > d[["open", "close", "high"]].min(axis=1))
    if bad.any():
        raise ValueError("invalid OHLC bounds")
    return d


def rma(s, n=14):
    x = s.to_numpy(float)
    out = np.full(len(x), np.nan)
    if len(x) < n or not np.isfinite(x[:n]).all():
        return pd.Series(out, index=s.index)
    out[n-1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = (out[i-1] * (n-1) + x[i]) / n if np.isfinite(x[i]) else np.nan
    return pd.Series(out, index=s.index)


def prepare(raw):
    d = raw.sort_index().copy()
    d["segment"] = d.index.to_series().diff().ne(BAR).cumsum().astype(int)
    d["atr"] = np.nan
    d["relvol"] = np.nan
    for ch in CHANNELS:
        d[f"hi{ch}"] = np.nan
        d[f"lo{ch}"] = np.nan
    for _, g in d.groupby("segment", sort=False):
        ix = g.index
        prev = g.close.shift(1)
        tr = pd.concat([g.high-g.low, (g.high-prev).abs(), (g.low-prev).abs()], axis=1).max(axis=1)
        d.loc[ix, "atr"] = rma(tr, 14).to_numpy()
        for ch in CHANNELS:
            d.loc[ix, f"hi{ch}"] = g.high.shift(1).rolling(ch, min_periods=ch).max().to_numpy()
            d.loc[ix, f"lo{ch}"] = g.low.shift(1).rolling(ch, min_periods=ch).min().to_numpy()
        med = g.volume.shift(1).rolling(96, min_periods=24).median().replace(0, np.nan)
        d.loc[ix, "relvol"] = (g.volume / med).to_numpy()

    h = d[["open", "high", "low", "close"]].resample("1h", label="right", closed="left").agg(
        {"open":"first", "high":"max", "low":"min", "close":"last"})
    count = d.close.resample("1h", label="right", closed="left").count()
    nseg = d.segment.resample("1h", label="right", closed="left").nunique()
    h = h.loc[count.eq(4) & nseg.eq(1)].dropna()
    hs = h.index.to_series().diff().ne(HOUR).cumsum()
    h["ema50"] = h.groupby(hs).close.transform(lambda x: x.ewm(span=50, adjust=False, min_periods=50).mean())
    d["hclose"] = h.close.reindex(d.index, method="ffill")
    d["hema"] = h.ema50.reindex(d.index, method="ffill")
    d["regime"] = np.select([d.hclose > d.hema, d.hclose < d.hema], ["bull", "bear"], default="mixed_or_unavailable")
    return d


def signals(d, ch, buf, tol, window, confirm):
    op, hi, lo, cl = (d[c].to_numpy(float) for c in ("open","high","low","close"))
    atr, seg = d.atr.to_numpy(float), d.segment.to_numpy()
    upper, lower = d[f"hi{ch}"].to_numpy(float), d[f"lo{ch}"].to_numpy(float)
    out, i, n = [], 0, len(d)
    while i < n-2:
        if seg[i] != seg[i+1] or not np.isfinite([upper[i],lower[i],atr[i]]).all() or atr[i] <= 0:
            i += 1
            continue
        side = "long" if cl[i] > upper[i] + buf*atr[i] else ("short" if cl[i] < lower[i] - buf*atr[i] else None)
        if side is None:
            i += 1
            continue
        level = upper[i] if side == "long" else lower[i]
        last = min(i+window, n-2)
        resolved, j = False, i
        for j in range(i+1,last+1):
            if seg[j] != seg[i] or seg[j+1] != seg[i]:
                resolved = True
                break
            touch = lo[j] <= level + tol*atr[i] and hi[j] >= level - tol*atr[i]
            held = cl[j] > level if side == "long" else cl[j] < level
            body = cl[j] > op[j] if side == "long" else cl[j] < op[j]
            if touch:
                ok = held and (confirm == "close_hold" or body)
                if ok and np.isfinite(atr[j]) and atr[j] > 0:
                    out.append({"break_i":i,"signal_i":j,"entry_i":j+1,"side":side,
                        "level":float(level),"atr":float(atr[j]),"retest_hi":float(hi[j]),"retest_lo":float(lo[j])})
                resolved = True
                break
            if (side == "long" and cl[j] <= level) or (side == "short" and cl[j] >= level):
                resolved = True
                break
        i = j+1 if resolved else last+1
    return out


def fill(direction, op, hi, lo, stop, target):
    if direction == 1:
        if lo <= stop: return (min(op,stop) if op < stop else stop), "SL"
        if hi >= target: return target, "TP"
    else:
        if hi >= stop: return (max(op,stop) if op > stop else stop), "SL"
        if lo <= target: return target, "TP"
    return None, None


def metrics(t):
    if t.empty:
        return {"trades":0,"win_rate_pct":0.0,"profit_factor":None,"net_R":0.0,"avg_R":0.0,
                "max_drawdown_R":0.0,"max_losing_streak":0,"positive_months_pct":0.0}
    x=t.sort_values("entry_time")
    r=x.net_R.to_numpy(float); win=r[r>0]; loss=r[r<0]
    eq=np.r_[0.0,np.cumsum(r)]; dd=eq-np.maximum.accumulate(eq)
    streak=mx=0
    for v in r:
        streak=streak+1 if v<0 else 0
        mx=max(mx,streak)
    mon=x.assign(month=x.exit_time.dt.strftime("%Y-%m")).groupby("month").net_R.sum()
    return {"trades":len(x),"win_rate_pct":100*float((r>0).mean()),
        "profit_factor":float(win.sum()/abs(loss.sum())) if len(loss) else float("inf"),
        "net_R":float(r.sum()),"avg_R":float(r.mean()),"max_drawdown_R":float(dd.min()),
        "max_losing_streak":mx,"positive_months_pct":100*float((mon>0).mean()),
        "tp":int((x.outcome=="TP").sum()),"sl":int((x.outcome=="SL").sum()),
        "time":int((x.outcome=="TIME").sum()),"long_trades":int((x.side=="long").sum()),
        "short_trades":int((x.side=="short").sum())}


def simulate(d, sigs, cfg, sample, start, end, cost):
    op,hi,lo,cl=(d[c].to_numpy(float) for c in ("open","high","low","close"))
    seg=d.segment.to_numpy(); hclose=d.hclose.to_numpy(float); hema=d.hema.to_numpy(float)
    rv=d.relvol.to_numpy(float); regime=d.regime.to_numpy(); idx=d.index
    rows=[]; last_exit=start-1
    for s in sigs:
        bi,si,ei=s["break_i"],s["signal_i"],s["entry_i"]
        if bi<start or si<start or ei>=end or ei<=last_exit or ei+MAX_HOLD>end: continue
        if seg[bi]!=seg[si] or not np.all(seg[ei:ei+MAX_HOLD]==seg[ei]): continue
        side=s["side"]
        if cfg["direction"]=="long_only" and side!="long": continue
        if cfg["direction"]=="short_only" and side!="short": continue
        if cfg["session"]=="07-19" and not 7<=idx[ei].hour<19: continue
        if cfg["volume_filter"]=="relvol1p5" and (not np.isfinite(rv[bi]) or rv[bi]<1.5): continue
        if cfg["filter"]=="ema50":
            if not np.isfinite([hclose[si],hema[si]]).all(): continue
            if (side=="long" and hclose[si]<=hema[si]) or (side=="short" and hclose[si]>=hema[si]): continue
        entry=float(op[ei])
        if cfg["stop"]=="retest_extreme":
            stop=s["retest_lo"]-0.1*s["atr"] if side=="long" else s["retest_hi"]+0.1*s["atr"]
        else:
            stop=entry-1.5*s["atr"] if side=="long" else entry+1.5*s["atr"]
        risk=entry-stop if side=="long" else stop-entry
        if not np.isfinite(risk) or risk<=0 or risk/entry>0.05: continue
        target=entry+cfg["target"]*risk if side=="long" else entry-cfg["target"]*risk
        direction=1 if side=="long" else -1
        exitp=float(cl[ei+MAX_HOLD-1]); exiti=ei+MAX_HOLD-1; outcome="TIME"
        for j in range(ei,ei+MAX_HOLD):
            fp,why=fill(direction,float(op[j]),float(hi[j]),float(lo[j]),stop,target)
            if why: exitp,outcome,exiti=float(fp),why,j; break
        gross=direction*(exitp-entry)/risk
        cost_r=(cost/10000)*entry/risk
        rows.append({"config_id":"|".join(str(cfg[k]) for k in ("channel","buffer","tolerance","window","confirm","stop","target","filter","direction","session","volume_filter")),"sample":sample,"breakout_time":idx[bi],"signal_time":idx[si],"entry_time":idx[ei],
            "exit_time":idx[exiti],"side":side,"channel":cfg["channel"],"buffer":cfg["buffer"],
            "tolerance":cfg["tolerance"],"window":cfg["window"],"confirm":cfg["confirm"],
            "stop":cfg["stop"],"target":cfg["target"],"filter":cfg["filter"],"direction":cfg["direction"],
            "session":cfg["session"],"volume_filter":cfg["volume_filter"],"entry":entry,"stop_price":stop,
            "target_price":target,"exit":exitp,"outcome":outcome,"gross_R":gross,"cost_R":cost_r,
            "net_R":gross-cost_r,"relvol":rv[bi],"regime":str(regime[ei]),"hold_bars":exiti-ei+1})
        last_exit=exiti
    return pd.DataFrame(rows)


def run(csv, out):
    out.mkdir(parents=True,exist_ok=True)
    raw=load_csv(csv); d=prepare(raw)
    if len(d)<10000: raise ValueError(f"insufficient 15m rows: {len(d)}")
    n=len(d); tr_end=int(n*.70); va_end=int(n*.85)
    bounds={"train":(0,tr_end),"validation":(tr_end,va_end),"oos":(va_end,n)}
    cache={}
    for key in itertools.product(CHANNELS,BUFFERS,TOLERANCES,WINDOWS,CONFIRMS):
        cache[key]=signals(d,*key)
    configs=[]
    for vals in itertools.product(CHANNELS,BUFFERS,TOLERANCES,WINDOWS,CONFIRMS,STOPS,TARGETS,FILTERS,DIRECTIONS,SESSIONS,VOLUME_FILTERS):
        ch,buf,tol,win,conf,stop,target,filt,direction,session,vol=vals
        configs.append({"channel":ch,"buffer":buf,"tolerance":tol,"window":win,"confirm":conf,
            "stop":stop,"target":target,"filter":filt,"direction":direction,"session":session,"volume_filter":vol})
    rows=[]
    for c in configs:
        sigs=cache[(c["channel"],c["buffer"],c["tolerance"],c["window"],c["confirm"])]
        t=simulate(d,sigs,c,"train",*bounds["train"],12)
        v=simulate(d,sigs,c,"validation",*bounds["validation"],12)
        mt,mv=metrics(t),metrics(v); r=dict(c)
        r.update({"train_"+k:v for k,v in mt.items()}); r.update({"validation_"+k:v for k,v in mv.items()})
        r["train_gate"]=mt["trades"]>=MIN_TRAIN and mt["net_R"]>0 and mt["profit_factor"]>=1.05 and mt["max_drawdown_R"]>=-25 and mt["positive_months_pct"]>=50
        r["validation_gate"]=r["train_gate"] and mv["trades"]>=MIN_VAL and mv["net_R"]>0 and mv["profit_factor"]>=1.05 and mv["max_drawdown_R"]>=-15 and mv["positive_months_pct"]>=50
        rows.append(r)
    m=pd.DataFrame(rows); m.to_csv(out/"matrix.csv",index=False)
    eligible=m[m.train_gate].copy()
    if len(eligible):
        eligible["score"]=eligible.train_net_R/(eligible.train_max_drawdown_R.abs()+1)
        short=eligible.sort_values(["score","train_trades"],ascending=False).head(SHORTLIST)
    else: short=eligible
    passes=short[short.validation_gate].copy()
    selected=None
    if len(passes):
        passes["score"]=passes.validation_net_R/(passes.validation_max_drawdown_R.abs()+1)
        selected=passes.sort_values(["score","validation_trades"],ascending=False).iloc[0].to_dict()
    cost_rows=[]; trade_frames=[]
    for r in short.to_dict("records"):
        c={k:r[k] for k in configs[0]}
        sigs=cache[(c["channel"],c["buffer"],c["tolerance"],c["window"],c["confirm"])]
        for sample in ("train","validation"):
            st,en=bounds[sample]
            for cost in COSTS:
                z=simulate(d,sigs,c,sample,st,en,cost)
                cost_rows.append({**c,"sample":sample,"cost_bps":cost,**metrics(z)})
            z=simulate(d,sigs,c,sample,st,en,12)
            if len(z): trade_frames.append(z)
        if selected is not None and all(r[k]==selected[k] for k in configs[0]):
            st,en=bounds["oos"]
            for cost in COSTS:
                z=simulate(d,sigs,c,"oos",st,en,cost)
                cost_rows.append({**c,"sample":"oos","cost_bps":cost,**metrics(z)})
            z=simulate(d,sigs,c,"oos",st,en,12)
            if len(z): trade_frames.append(z)
    pd.DataFrame(cost_rows).to_csv(out/"cost_sensitivity.csv",index=False)
    if trade_frames:
        trades=pd.concat(trade_frames,ignore_index=True); trades.to_csv(out/"selected_trades_12bp.csv",index=False)
        trades.assign(month=trades.exit_time.dt.strftime("%Y-%m")).groupby(["config_id","sample","month"]).net_R.agg(["count","sum","mean"]).reset_index().to_csv(out/"monthly.csv",index=False)
        trades.groupby(["config_id","sample","regime"]).net_R.agg(["count","sum","mean"]).reset_index().to_csv(out/"regimes.csv",index=False)
    else:
        pd.DataFrame().to_csv(out/"selected_trades_12bp.csv",index=False)
        pd.DataFrame().to_csv(out/"monthly.csv",index=False); pd.DataFrame().to_csv(out/"regimes.csv",index=False)
    meta={"classification":"experimental price-only backtest","symbol":"BTCUSD","timeframe":"15m",
        "rows":len(d),"start_utc":d.index.min().isoformat(),"end_utc":d.index.max().isoformat(),
        "gaps":int((d.index.to_series().diff().dropna()!=BAR).sum()),"zero_volume_bars":int((d.volume==0).sum()),
        "sha256":sha(csv),"train_end_utc":d.index[tr_end-1].isoformat(),"validation_end_utc":d.index[va_end-1].isoformat(),
        "configurations":len(configs),"train_eligible":int(m.train_gate.sum()),"shortlisted":len(short),
        "validation_passes":len(passes),"oos_evaluated":selected is not None,
        "costs":"6/12/20bp assumed round-trip; 12bp primary; no funding or separate spread/slippage model",
        "execution":"next 15m open after first retest hold; stop-first; adverse stop gaps at worse open; fixed target fill; 8h max hold",
        "split":"chronological 70/15/15; breakout, retest, entry and full hold kept inside split and contiguous segment",
        "rules":"Donchian 20/40 breakout; 0/0.1 ATR buffer; first retest within 4/8 bars and 0.1/0.25 ATR tolerance; close-hold/directional body; retest-extreme/1.5 ATR stops; 1.5/2/3R targets; optional completed 1H EMA50 and 1.5x prior 96-bar median volume filters"}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    summary=["# BTCUSD Donchian breakout-retest intraday study","",
        f"- Dataset: {len(d):,} 15m bars, {d.index.min()} to {d.index.max()}, {meta['gaps']} gaps.",
        f"- SHA-256: {meta['sha256']}",
        f"- Matrix: {len(configs)} configs; {meta['train_eligible']} train-eligible; {meta['shortlisted']} shortlisted; {meta['validation_passes']} validation passes.",
        f"- Boundaries: train through {meta['train_end_utc']}; validation through {meta['validation_end_utc']}.",
        "- Primary cost 12bp round-trip; sensitivity 6/12/20bp."]
    summary.append("OOS not evaluated: no candidate passed both gates." if selected is None else "One validation-selected candidate evaluated once on untouched OOS.")
    (out/"summary.md").write_text("\n".join(summary)+"\n")
    print("\n".join(summary))
    return meta


def self_test():
    assert fill(1,100,120,80,90,110)==(90,"SL")
    assert fill(-1,100,120,80,110,90)==(110,"SL")
    assert fill(1,85,95,80,90,110)==(85,"SL")
    assert fill(1,115,120,112,90,110)==(110,"TP")
    ix=pd.date_range("2025-01-01",periods=12,freq="15min",tz="UTC")
    x=pd.DataFrame({"open":[99,99,100,100.2,100.8,101,101,101,101,101,101,101],
        "high":[100,100,102,101,102,102,102,102,102,102,102,102],
        "low":[98,98,99.5,100.05,100.5,100,100,100,100,100,100,100],
        "close":[99,99,101,100.8,101.5,101,101,101,101,101,101,101],
        "atr":np.ones(12),"segment":np.zeros(12,dtype=int),
        "hi20":[100,100,100,100,102,102,102,102,102,102,102,102],
        "lo20":[90]*12},index=ix)
    s=signals(x,20,0,.1,4,"close_hold")
    assert len(s)==1 and s[0]["break_i"]==2 and s[0]["signal_i"]==3 and s[0]["entry_i"]==4
    bad=x.copy(); bad.loc[ix[3],"close"]=99.8
    assert not signals(bad,20,0,.1,4,"close_hold")
    bearish=x.copy(); bearish.loc[ix[3],"open"]=101
    assert not signals(bearish,20,0,.1,4,"directional_body")
    print("7 Donchian retest causality/execution tests passed")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--price-csv",type=Path); p.add_argument("--output-dir",type=Path)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test: self_test(); return
    if not a.price_csv or not a.output_dir: p.error("provide --price-csv and --output-dir")
    run(a.price_csv,a.output_dir)


if __name__=="__main__": main()
