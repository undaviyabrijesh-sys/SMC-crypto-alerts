from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
LOOKBACK_HOURS = (1, 4, 8)
THRESHOLDS = (0.0025, 0.0050)  # 0.25pp, 0.50pp relative return spread
HOLD_HOURS = (1, 2, 4)
MODES = ("pair", "long_stronger")
COSTS_BPS = (6, 12, 20)
FUNDING_TIMES = {0, 8, 16}


def load_pair(btc_path: Path, eth_path: Path):
    frames=[]
    for p in (btc_path, eth_path):
        d=pd.read_csv(p,parse_dates=["timestamp"]).set_index("timestamp").sort_index()
        d.index=pd.to_datetime(d.index,utc=True)
        if d.index.has_duplicates: raise ValueError(f"Duplicate timestamps in {p}: {int(d.index.duplicated().sum())}")
        for c in ("open","high","low","close","volume"):
            d[c]=pd.to_numeric(d[c],errors="coerce")
        o=d[["open","high","low","close"]].to_numpy(float)
        if not np.isfinite(o).all() or not (o>0).all():
            raise ValueError(f"Invalid or non-positive OHLC values in {p}")
        bad=(d.high<d[["open","close","low"]].max(axis=1)) | (d.low>d[["open","close","high"]].min(axis=1))
        if bad.any(): raise ValueError(f"Invalid OHLC geometry in {p}: {int(bad.sum())} rows")
        if (d.volume<0).any(): raise ValueError(f"Negative volume in {p}")
        frames.append(d)
    b,e=frames
    btc_only=int(len(b.index.difference(e.index))); eth_only=int(len(e.index.difference(b.index)))
    common=b.index.intersection(e.index)
    b=b.loc[common]; e=e.loc[common]
    if len(common)<1000: raise ValueError("Insufficient aligned data")
    expected=pd.date_range(common[0],common[-1],freq=BAR,tz="UTC")
    if not common.equals(expected): raise ValueError("Aligned data has gaps or irregular timestamps")
    b.attrs["btc_only_timestamps"]=btc_only
    b.attrs["eth_only_timestamps"]=eth_only
    return b,e


def regime_map(btc: pd.DataFrame):
    # Completed 4h bars, with EMA50/EMA200 computed only from completed 4h closes.
    x=btc.copy()
    x.index=x.index+BAR
    x=x.resample("4h",label="right",closed="right",origin="epoch").agg(
        open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),
        bar_count=("close","count")
    )
    x=x[x.bar_count==16].drop(columns="bar_count").dropna()
    x["ema50"]=x.close.ewm(span=50,adjust=False,min_periods=50).mean()
    x["ema200"]=x.close.ewm(span=200,adjust=False,min_periods=200).mean()
    x["regime"]=np.where(x.ema50>x.ema200,"bull",np.where(x.ema50<x.ema200,"bear","neutral"))
    return x.regime


def funding_crosses(start: pd.Timestamp, end: pd.Timestamp):
    # An entry at a settlement timestamp is assumed to occur after that settlement.
    t=start.floor("h") + pd.Timedelta(hours=1)
    while t <= end:
        if t.hour in FUNDING_TIMES and t.minute==0: return True
        t += pd.Timedelta(hours=1)
    return False


def metrics(rets: pd.Series, trades: pd.DataFrame):
    r=rets.dropna().astype(float)
    if len(r)==0:
        return {"trades":0,"win_rate_pct":None,"profit_factor":None,"net_return_pct":None,
                "avg_trade_pct":None,"max_drawdown_pct":None,"max_losing_streak":0,
                "positive_months_pct":None,"positive_months":0,"active_months":0}
    pos=r[r>0].sum(); neg=-r[r<0].sum()
    pf=float(pos/neg) if neg>0 else (float("inf") if pos>0 else 0.0)
    eq=(1+r).cumprod(); dd=eq/eq.cummax()-1
    streak=cur=0
    for v in r:
        if v<0: cur+=1; streak=max(streak,cur)
        else: cur=0
    month_frame=pd.DataFrame({"exit_time":pd.to_datetime(trades.exit_time,utc=True),"net":r.to_numpy()})
    monthly=month_frame.assign(month=month_frame.exit_time.dt.strftime("%Y-%m")).groupby("month").net.sum()
    return {"trades":int(len(r)),"win_rate_pct":float((r>0).mean()*100),"profit_factor":pf,
            "net_return_pct":float((eq.iloc[-1]-1)*100),"avg_trade_pct":float(r.mean()*100),
            "max_drawdown_pct":float(dd.min()*100),"max_losing_streak":int(streak),
            "positive_months_pct":float((monthly>0).mean()*100) if len(monthly) else None,
            "positive_months":int((monthly>0).sum()),"active_months":int(len(monthly))}


def relative_spread_series(btc: pd.DataFrame, eth: pd.DataFrame, lookback_bars: int):
    return btc.close.pct_change(lookback_bars,fill_method=None)-eth.close.pct_change(lookback_bars,fill_method=None)


def build_trades(btc,eth,regimes,split_idx,lookback_h,threshold,hold_h,mode,spread_series,decision_indices):
    n=len(btc); lb=lookback_h*4; hold=hold_h*4
    decisions=decision_indices[(decision_indices>=lb)&(decision_indices<n-hold-1)]
    if len(decisions)==0: return pd.DataFrame()
    entry_idx=decisions+1; exit_idx=entry_idx+hold-1
    spread_values=spread_series.to_numpy()[decisions]
    valid=np.isfinite(spread_values)&(np.abs(spread_values)>=threshold)
    train_ok=(entry_idx<split_idx[0])&(exit_idx<split_idx[0])
    val_ok=(entry_idx>=split_idx[0])&(exit_idx<split_idx[1])
    valid &= train_ok|val_ok
    entry_hours=np.array([btc.index[j].hour for j in entry_idx],dtype=int)
    crosses=np.zeros(len(entry_idx),dtype=bool)
    for step in range(1,hold_h+1):
        crosses |= np.isin((entry_hours+step)%24,[0,8,16])
    valid &= ~crosses
    cand=np.flatnonzero(valid)
    rows=[]; last_exit=-1
    btc_open=btc.open.to_numpy(float); btc_close=btc.close.to_numpy(float)
    eth_open=eth.open.to_numpy(float); eth_close=eth.close.to_numpy(float)
    for k in cand:
        i=int(decisions[k]); ei=int(entry_idx[k]); xi=int(exit_idx[k])
        if ei<=last_exit: continue
        s=float(spread_values[k]); strong="BTC" if s>0 else "ETH"
        if mode=="pair":
            if strong=="BTC":
                lr=btc_close[xi]/btc_open[ei]-1; sr=eth_close[xi]/eth_open[ei]-1
            else:
                lr=eth_close[xi]/eth_open[ei]-1; sr=btc_close[xi]/btc_open[ei]-1
            gross=(lr-sr)/2
            short_asset="ETH" if strong=="BTC" else "BTC"
        else:
            lr=(btc_close[xi]/btc_open[ei]-1) if strong=="BTC" else (eth_close[xi]/eth_open[ei]-1)
            sr=np.nan; gross=lr; short_asset=""
        decision=btc.index[i]+BAR; entry_time=btc.index[ei]; exit_time=btc.index[xi]+BAR
        sample="train" if ei<split_idx[0] else "validation"
        rows.append({"sample":sample,"signal_time":decision.isoformat(),"entry_time":entry_time.isoformat(),
                     "exit_time":exit_time.isoformat(),"lookback_h":lookback_h,"threshold":threshold,
                     "hold_h":hold_h,"mode":mode,"relative_spread":s,"strong_asset":strong,
                     "long_asset":strong,"short_asset":short_asset,"long_leg_return":float(lr),
                     "short_leg_return":float(sr) if np.isfinite(sr) else None,"gross_return":float(gross),
                     "regime_4h_ema50_200":str(regimes.iloc[i])})
        last_exit=xi
    return pd.DataFrame(rows)


def run(btc,eth,out,args):
    n=len(btc); train_end=int(n*.70); val_end=int(n*.85)
    raw_regimes=regime_map(btc)
    decision_times=btc.index+BAR
    regimes=raw_regimes.reindex(decision_times,method="ffill").fillna("unknown")
    all_rows=[]; summaries=[]; costs=[]; monthly=[]; regimes_out=[]
    decision_indices=np.flatnonzero((btc.index.minute==45))
    spread_by_lookback={lb:relative_spread_series(btc,eth,lb*4) for lb in LOOKBACK_HOURS}
    for lb in LOOKBACK_HOURS:
        for th in THRESHOLDS:
            for hold in HOLD_HOURS:
                for mode in MODES:
                    t=build_trades(btc,eth,regimes,(train_end,val_end),lb,th,hold,mode,spread_by_lookback[lb],decision_indices)
                    if t.empty:
                        for sample in ("train","validation"):
                            summaries.append({"lookback_h":lb,"threshold_pct":th*100,"hold_h":hold,"mode":mode,"sample":sample,**metrics(pd.Series(dtype=float),t)})
                        continue
                    for cost in COSTS_BPS:
                        for sample in ("train","validation"):
                            sub=t[t["sample"]==sample].copy()
                            r=sub.gross_return-cost/10000
                            m=metrics(r,sub)
                            costs.append({"lookback_h":lb,"threshold_pct":th*100,"hold_h":hold,"mode":mode,"sample":sample,"cost_bps":cost,**m})
                            if cost==12:
                                summaries.append({"lookback_h":lb,"threshold_pct":th*100,"hold_h":hold,"mode":mode,"sample":sample,**m})
                                if len(sub):
                                    z=sub.copy(); z["net_return"]=r.values
                                    z["month"]=pd.to_datetime(z.exit_time,utc=True).dt.strftime("%Y-%m")
                                    for month,g in z.groupby("month"):
                                        monthly.append({"lookback_h":lb,"threshold_pct":th*100,"hold_h":hold,"mode":mode,"sample":sample,"month":month,"trades":len(g),"net_return_pct":g.net_return.sum()*100})
                                    for regime,g in z.groupby("regime_4h_ema50_200"):
                                        regimes_out.append({"lookback_h":lb,"threshold_pct":th*100,"hold_h":hold,"mode":mode,"sample":sample,"regime":regime,"trades":len(g),"net_return_pct":g.net_return.sum()*100,"win_rate_pct":(g.net_return>0).mean()*100})
                    all_rows.extend(t.to_dict("records"))
    matrix=pd.DataFrame(summaries)
    train_mask=matrix["sample"].eq("train")
    matrix["train_gate"]=False
    matrix.loc[train_mask,"train_gate"]=(matrix.loc[train_mask,"trades"].ge(100)&matrix.loc[train_mask,"profit_factor"].ge(1.05)&matrix.loc[train_mask,"net_return_pct"].gt(0)&matrix.loc[train_mask,"positive_months_pct"].ge(50))
    train=matrix[train_mask][["lookback_h","threshold_pct","hold_h","mode","train_gate"]].rename(columns={"train_gate":"paired_train_gate"})
    matrix=matrix.merge(train,on=["lookback_h","threshold_pct","hold_h","mode"],how="left")
    matrix["validation_gate"]=(matrix["sample"].eq("validation")&matrix.trades.ge(50)&matrix.profit_factor.ge(1.05)&matrix.net_return_pct.gt(0)&matrix.positive_months_pct.ge(50))
    passed=matrix[(matrix["sample"]=="validation")&matrix.paired_train_gate.fillna(False)&matrix.validation_gate]
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(all_rows).to_csv(out/"trades_12bp_gross.csv",index=False)
    matrix.to_csv(out/"matrix_12bp.csv",index=False)
    pd.DataFrame(costs).to_csv(out/"cost_sensitivity.csv",index=False)
    pd.DataFrame(monthly).to_csv(out/"monthly.csv",index=False)
    pd.DataFrame(regimes_out).to_csv(out/"regimes.csv",index=False)
    meta={"classification":"experimental; two-asset cross-sectional study only; no live use",
          "assets":"Delta Exchange India BTCUSD and ETHUSD perpetual traded-price 15m candles",
          "rows":n,"start_utc":btc.index[0].isoformat(),"last_bar_open_utc":btc.index[-1].isoformat(),
          "train_end_row":train_end,"validation_end_row":val_end,
          "train_end_time_utc":btc.index[train_end-1].isoformat(),"validation_end_time_utc":btc.index[val_end-1].isoformat(),
          "gaps":"none in both aligned source datasets; exact common timestamps only",
          "btc_only_timestamps":int(btc.attrs.get("btc_only_timestamps",0)),"eth_only_timestamps":int(btc.attrs.get("eth_only_timestamps",0)),
          "lookbacks_hours":LOOKBACK_HOURS,"relative_spread_thresholds_pct":[x*100 for x in THRESHOLDS],
          "holding_hours":HOLD_HOURS,"modes":MODES,"decision_frequency":"hourly UTC boundaries; signal at completed 15m close; enter next 15m open",
          "position_rule":"one position per configuration at a time; skip overlapping decisions; pair = equal-dollar long stronger and short weaker; long_stronger = long stronger asset only",
          "exit_rule":"fixed horizon close; no stops or targets; entire trade must remain inside its chronological split",
          "funding":"positions crossing UTC 00:00, 08:00 or 16:00 settlement boundaries excluded; no funding cashflow model applied",
          "costs":"6/12/20 bps round-trip per leg; 12bp primary; for equal-dollar pair the same bps is charged on total gross pair notional",
          "filters":"none; completed 4h EMA50/EMA200 used only for attribution",
          "gate":"train >=100 trades, PF>=1.05, net return>0, positive active months>=50%; validation >=50 trades with same PF/net/month gates; no OOS unless both pass",
          "validation_passes":int(len(passed)),"oos_evaluated":False,
          "btc_sha256":hashlib.sha256(Path(args.btc).read_bytes()).hexdigest(),"eth_sha256":hashlib.sha256(Path(args.eth).read_bytes()).hexdigest()}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps(meta,indent=2))
    print("\nTOP TRAIN CONFIGS")
    print(matrix[matrix["sample"]=="train"].sort_values(["net_return_pct","profit_factor"],ascending=False).head(12).to_string(index=False))
    print("\nVALIDATION GATE PASSES")
    print(passed.to_string(index=False) if len(passed) else "None")
    print("\nTOP VALIDATION DIAGNOSTICS (NOT SELECTED)")
    print(matrix[matrix["sample"]=="validation"].sort_values(["net_return_pct","profit_factor"],ascending=False).head(12).to_string(index=False))


def relative_spread_series_for_test(btc,eth,lookback_bars):
    return relative_spread_series(btc,eth,lookback_bars)


def load_pair_from_frames(b,e):
    common=b.index.intersection(e.index)
    return b.loc[common],e.loc[common]


def self_test():
    idx=pd.date_range("2026-01-01 00:00",periods=100,freq="15min",tz="UTC")
    x=pd.DataFrame({"open":np.linspace(100,110,100),"high":np.linspace(101,111,100),"low":np.linspace(99,109,100),"close":np.linspace(100.5,110.5,100),"volume":1},index=idx)
    y=x.copy(); y.close*=1.01; y.open*=1.01
    b,e=load_pair_from_frames(x,y)
    assert len(b)==100 and len(e)==100 and b.index.equals(e.index)
    assert funding_crosses(pd.Timestamp("2026-01-01 07:00",tz="UTC"),pd.Timestamp("2026-01-01 08:00",tz="UTC"))
    assert not funding_crosses(pd.Timestamp("2026-01-01 08:00",tz="UTC"),pd.Timestamp("2026-01-01 09:00",tz="UTC"))
    s1=relative_spread_series(b,e,4)
    b2=b.copy(); e2=e.copy(); b2.iloc[60:,b2.columns.get_loc("close")]*=1.20; e2.iloc[60:,e2.columns.get_loc("close")]*=0.80
    s2=relative_spread_series(b2,e2,4)
    assert np.allclose(s1.iloc[:60].to_numpy(),s2.iloc[:60].to_numpy(),equal_nan=True)
    big_idx=pd.date_range("2026-01-01 00:00",periods=5000,freq="15min",tz="UTC")
    px=100*np.exp(np.arange(5000)*0.00005 + 0.01*np.sin(np.arange(5000)/50))
    big=pd.DataFrame({"open":px,"high":px*1.002,"low":px*.998,"close":px,"volume":1},index=big_idx)
    r1=regime_map(big)
    big2=big.copy(); big2.iloc[4000:,big2.columns.get_loc("close")]*=0.7
    r2=regime_map(big2)
    cutoff=big.index[3999]+BAR
    assert r1.loc[:cutoff].equals(r2.loc[:cutoff])
    assert all((r1.index.minute==0)&(r1.index.hour%4==0))
    print("5 synthetic alignment/funding/no-lookahead/full-4h-bar tests passed")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--btc",required=False); p.add_argument("--eth",required=False); p.add_argument("--out",required=False)
    p.add_argument("--self-test",action="store_true"); args=p.parse_args()
    if args.self_test: self_test()
    else:
        if not (args.btc and args.eth and args.out): p.error("--btc, --eth and --out are required unless --self-test is used")
        btc,eth=load_pair(Path(args.btc),Path(args.eth)); run(btc,eth,Path(args.out),args)
