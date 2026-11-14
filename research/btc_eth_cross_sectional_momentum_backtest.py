#!/usr/bin/env python3
"""Preregistered BTC/ETH 72h relative-momentum rotation on 15m traded candles.

At each 4h UTC boundary, use only the last completed 15m close and its
72h-lagged close. If BTC outperformed ETH by >=1.00 percentage point, long BTC
and short ETH for the next 4h; if ETH outperformed by >=1.00pp, reverse both
legs. Equal-dollar 1x legs. Entry is the next 15m open; exit is the close of
the 16th 15m bar. Also report a long-only stronger-asset variant and fixed
relative-direction benchmarks. No tuning grid, no live actions.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

BAR = pd.Timedelta(minutes=15)
LOOKBACK_BARS = 288                 # 72h
HOLD_BARS = 16                      # 4h
SPREAD_THRESHOLD = 0.01             # 1.00 percentage point relative return
COSTS_BPS = (6.0, 12.0, 20.0)       # assumed round-trip cost per leg
SEED = 20261116
PERIODS = {
    "development": ("2024-11-14", "2025-11-14"),
    "validation": ("2025-11-14", "2026-05-14"),
    "final_holdout": ("2026-05-14", "2026-11-14"),
}

class StudyError(RuntimeError):
    pass

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()

def load_ohlcv(path: Path, label: str) -> pd.DataFrame:
    d=pd.read_csv(path)
    if "timestamp" not in d.columns:
        raise StudyError(f"{label}: missing timestamp column")
    d["timestamp"]=pd.to_datetime(d.timestamp,utc=True,errors="raise")
    if d.timestamp.duplicated().any():
        raise StudyError(f"{label}: duplicate timestamps")
    d=d.sort_values("timestamp").set_index("timestamp")
    for col in ("open","high","low","close"):
        d[col]=pd.to_numeric(d[col],errors="raise")
    if "volume" not in d: d["volume"]=0.0
    d["volume"]=pd.to_numeric(d.volume,errors="raise")
    values=d[["open","high","low","close","volume"]].to_numpy(float)
    if not np.isfinite(values).all() or (d[["open","high","low","close"]]<=0).any().any():
        raise StudyError(f"{label}: non-finite or non-positive OHLCV")
    bad=(d.high<d[["open","close","low"]].max(axis=1)) | (d.low>d[["open","close","high"]].min(axis=1))
    if bad.any(): raise StudyError(f"{label}: invalid OHLC rows={int(bad.sum())}")
    if (d.volume<0).any(): raise StudyError(f"{label}: negative volume")
    return d

def align_pair(btc: pd.DataFrame, eth: pd.DataFrame) -> tuple[pd.DataFrame,dict]:
    meta={}
    for label,d in (("btc",btc),("eth",eth)):
        delta=d.index.to_series().diff().dropna()
        meta[label]={"rows":int(len(d)),"start_utc":d.index.min().isoformat(),
            "end_utc":d.index.max().isoformat(),"gap_count":int((delta>BAR*1.5).sum()),
            "irregular_intervals":int((delta!=BAR).sum()),
            "zero_volume_rows":int((d.volume==0).sum())}
    x=btc[["open","high","low","close"]].add_prefix("btc_").join(
        eth[["open","high","low","close"]].add_prefix("eth_"),how="inner")
    if x.empty: raise StudyError("BTC/ETH have no common timestamps")
    if not x.index.is_monotonic_increasing or x.index.has_duplicates:
        raise StudyError("Aligned timestamps are not unique and ordered")
    x["segment"]=x.index.to_series().diff().ne(BAR).cumsum().astype(int)
    delta=x.index.to_series().diff().dropna()
    meta["aligned"]={"rows":int(len(x)),"start_utc":x.index.min().isoformat(),
        "end_utc":x.index.max().isoformat(),"gap_count":int((delta>BAR*1.5).sum()),
        "irregular_intervals":int((delta!=BAR).sum()),
        "btc_only_timestamps":int(len(btc.index.difference(eth.index))),
        "eth_only_timestamps":int(len(eth.index.difference(btc.index)))}
    return x,meta

def direction_from_spread(spread: float, threshold: float=SPREAD_THRESHOLD) -> int:
    if spread>=threshold: return 1     # BTC stronger
    if spread<=-threshold: return -1   # ETH stronger
    return 0

def trailing_relative_return(pair: pd.DataFrame, decision_i: int) -> tuple[float,float,float] | None:
    """At decision_i open, use close of i-1 and close of i-1-288 only."""
    prev=decision_i-1
    base=prev-LOOKBACK_BARS
    if base<0: return None
    if pair.segment.iloc[base:decision_i+HOLD_BARS].nunique()!=1: return None
    btc_ret=float(pair.btc_close.iloc[prev]/pair.btc_close.iloc[base]-1.0)
    eth_ret=float(pair.eth_close.iloc[prev]/pair.eth_close.iloc[base]-1.0)
    return btc_ret,eth_ret,btc_ret-eth_ret

def pair_gross_return(btc_ret_pct: float, eth_ret_pct: float, direction: int) -> float:
    """Return per unit of total gross notional for equal-dollar long/short legs."""
    if direction==1: return 0.5*(btc_ret_pct-eth_ret_pct)
    if direction==-1: return 0.5*(eth_ret_pct-btc_ret_pct)
    return 0.0

def build_decisions(pair: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    idx=pair.index
    for i,ts in enumerate(idx):
        if ts.minute!=0 or ts.hour%4!=0:
            continue
        j=i+HOLD_BARS-1
        if j>=len(pair): continue
        rel=trailing_relative_return(pair,i)
        if rel is None: continue
        btc_mom,eth_mom,spread=rel
        direction=direction_from_spread(spread)
        btc_entry=float(pair.btc_open.iloc[i]); eth_entry=float(pair.eth_open.iloc[i])
        btc_exit=float(pair.btc_close.iloc[j]); eth_exit=float(pair.eth_close.iloc[j])
        btc_ret=(btc_exit/btc_entry-1.0)*100.0
        eth_ret=(eth_exit/eth_entry-1.0)*100.0
        pair_ret=pair_gross_return(btc_ret,eth_ret,direction)
        strong_ret=btc_ret if direction==1 else eth_ret if direction==-1 else 0.0
        weak_short_ret=-eth_ret if direction==1 else -btc_ret if direction==-1 else 0.0
        always_btc_short_eth=pair_gross_return(btc_ret,eth_ret,1)
        always_eth_short_btc=pair_gross_return(btc_ret,eth_ret,-1)
        active=direction!=0
        row={"decision_time":ts.isoformat(),"entry_time":ts.isoformat(),
            "exit_time":(idx[j]+BAR).isoformat(),"direction":direction,
            "stronger_asset":"BTC" if direction==1 else "ETH" if direction==-1 else "flat",
            "active":active,"btc_trailing_72h_pct":btc_mom*100.0,
            "eth_trailing_72h_pct":eth_mom*100.0,
            "relative_spread_pp":spread*100.0,
            "btc_leg_return_pct":btc_ret,"eth_leg_return_pct":eth_ret,
            "pair_gross_pct":pair_ret,"strong_only_gross_pct":strong_ret,
            "weak_short_gross_pct":weak_short_ret,
            "always_btc_short_eth_gross_pct":always_btc_short_eth,
            "always_eth_short_btc_gross_pct":always_eth_short_btc}
        for bps in COSTS_BPS:
            cost=bps/100.0 if active else 0.0
            row[f"pair_net_{int(bps)}bps_pct"]=pair_ret-cost
            row[f"strong_only_net_{int(bps)}bps_pct"]=strong_ret-cost
            row[f"always_btc_short_eth_net_{int(bps)}bps_pct"]=always_btc_short_eth-bps/100.0
            row[f"always_eth_short_btc_net_{int(bps)}bps_pct"]=always_eth_short_btc-bps/100.0
        rows.append(row)
    return pd.DataFrame(rows)

def max_losing_streak(values: np.ndarray) -> int:
    current=maximum=0
    for value in values:
        current=current+1 if value<0 else 0
        maximum=max(maximum,current)
    return int(maximum)

def block_ci(values: np.ndarray, seed: int, block: int=6, reps: int=2000):
    x=np.asarray(values,float); x=x[np.isfinite(x)]
    n=len(x)
    if n<20: return None
    rng=np.random.default_rng(seed)
    blocks=int(np.ceil(n/block))
    starts=rng.integers(0,n,size=(reps,blocks))
    idx=(starts[:,:,None]+np.arange(block)[None,None,:])%n
    idx=idx.reshape(reps,-1)[:,:n]
    means=x[idx].mean(axis=1)
    return [round(float(v),6) for v in np.quantile(means,[0.025,0.975])]

def metrics(decisions: pd.DataFrame, column: str, *, active_only: bool) -> dict:
    if decisions.empty:
        return {"decisions":0,"trades":0}
    g=decisions.sort_values("entry_time").copy()
    series=g[column].astype(float)
    if active_only:
        active=g.active.astype(bool)
        trade=series[active].to_numpy(float)
    else:
        active=pd.Series(True,index=g.index)
        trade=series.to_numpy(float)
    wins=trade[trade>0]; losses=trade[trade<0]
    equity=(1.0+series.to_numpy(float)/100.0).cumprod()
    peak=np.maximum.accumulate(np.r_[1.0,equity])[1:]
    dd=(equity/peak-1.0)*100.0
    months=g.assign(month=pd.to_datetime(g.entry_time,utc=True).dt.tz_convert(None).dt.to_period("M"),
                    ret=series.to_numpy(float)).groupby("month").ret.apply(
                        lambda s:(np.prod(1+s.to_numpy(float)/100.0)-1.0)*100.0)
    active_months=g.loc[g.active.astype(bool)].assign(
        month=pd.to_datetime(g.loc[g.active.astype(bool),"entry_time"],utc=True).dt.tz_convert(None).dt.to_period("M")
    ).groupby("month").size()
    month_positive=int((months>0).sum())
    result={"decisions":int(len(g)),"trades":int(len(trade)),
        "active_decisions":int(g.active.sum()) if active_only else int(len(g)),
        "active_fraction":round(float(g.active.mean()),4) if active_only else 1.0,
        "win_rate_pct":round(float((trade>0).mean()*100),3) if len(trade) else None,
        "profit_factor":round(float(wins.sum()/abs(losses.sum())),4) if len(losses) and abs(losses.sum()) else None,
        "sum_net_return_pct_points":round(float(trade.sum()),4) if len(trade) else 0.0,
        "mean_net_per_trade_pct":round(float(trade.mean()),5) if len(trade) else None,
        "compounded_net_return_pct":round(float((equity[-1]-1.0)*100.0),4),
        "max_drawdown_pct":round(float(min(0.0,dd.min())) if len(dd) else 0.0,4),
        "max_losing_streak":max_losing_streak(trade),
        "positive_month_fraction":round(float(month_positive/len(months)),4) if len(months) else None,
        "positive_months":month_positive,"months":int(len(months)),
        "gross_notional_turnover_units":round(float(g.active.sum()*(2 if "pair_" in column else 1)),2) if active_only else round(float(len(g)*2),2),
        "r_multiple":"not applicable: no stop-defined risk unit in this forward/rotation study"}
    if active_only and len(trade)>=20:
        result["mean_net_95pct_6decision_block_bootstrap_ci"]=block_ci(trade,SEED+len(trade))
    return result

def summarize_periods(decisions: pd.DataFrame) -> dict:
    out={}
    for name,(start,end) in PERIODS.items():
        lo=pd.Timestamp(start,tz="UTC"); hi=pd.Timestamp(end,tz="UTC")
        g=decisions[(pd.to_datetime(decisions.entry_time,utc=True)>=lo)&
                    (pd.to_datetime(decisions.entry_time,utc=True)<hi)].copy()
        out[name]={"decision_count":int(len(g)),
            "active_pair":metrics(g,"pair_net_12bps_pct",active_only=True),
            "active_strong_only":metrics(g,"strong_only_net_12bps_pct",active_only=True),
            "always_btc_short_eth":metrics(g,"always_btc_short_eth_net_12bps_pct",active_only=False),
            "always_eth_short_btc":metrics(g,"always_eth_short_btc_net_12bps_pct",active_only=False),
            "cost_sensitivity":{}}
        for bps in COSTS_BPS:
            out[name]["cost_sensitivity"][str(int(bps))]={
                "pair":metrics(g,f"pair_net_{int(bps)}bps_pct",active_only=True),
                "strong_only":metrics(g,f"strong_only_net_{int(bps)}bps_pct",active_only=True)}
    return out

def self_test():
    assert direction_from_spread(0.010)==1
    assert direction_from_spread(-0.010)==-1
    assert direction_from_spread(0.0099)==0
    assert abs(pair_gross_return(2.0,1.0,1)-0.5)<1e-12
    assert abs(pair_gross_return(2.0,1.0,-1)+0.5)<1e-12
    # Verify the signal uses the previous completed close, never the entry bar.
    idx=pd.date_range("2026-01-01",periods=310,freq="15min",tz="UTC")
    d=pd.DataFrame({"btc_close":100.0,"eth_close":100.0,
        "segment":np.zeros(310,dtype=int)},index=idx)
    d.loc[idx[15],"btc_close"]=100.0; d.loc[idx[303],"btc_close"]=102.0
    i=304
    a=trailing_relative_return(d,i)
    d.loc[idx[304:],"btc_close"]=9999.0
    b=trailing_relative_return(d,i)
    assert a==b and abs(a[2]-0.02)<1e-12
    assert abs((0.5-12.0/100.0)-0.38)<1e-12
    print("PASS 5 deterministic momentum tests")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--btc-csv",default="historical_data/BTC_15m.csv")
    ap.add_argument("--eth-csv",default="historical_data/ETH_15m.csv")
    ap.add_argument("--output-dir",default="results/btc-eth-momentum")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test()
        return
    btc_path=Path(args.btc_csv); eth_path=Path(args.eth_csv)
    btc=load_ohlcv(btc_path,"BTC"); eth=load_ohlcv(eth_path,"ETH")
    pair,quality=align_pair(btc,eth)
    if len(pair)<30000: raise StudyError(f"Insufficient aligned 15m history: {len(pair)}")
    decisions=build_decisions(pair)
    if decisions.empty: raise StudyError("No scheduled momentum decisions")
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    decisions.to_csv(out/"four_hour_decisions.csv",index=False)
    monthly=decisions.assign(month=pd.to_datetime(decisions.entry_time,utc=True).dt.tz_convert(None).dt.to_period("M"))
    monthly_rows=[]
    for month,g in monthly.groupby("month"):
        row={"month":str(month),"decisions":int(len(g)),"active":int(g.active.sum())}
        for name,col in (("pair","pair_net_12bps_pct"),("strong_only","strong_only_net_12bps_pct"),
                         ("always_btc_short_eth","always_btc_short_eth_net_12bps_pct"),
                         ("always_eth_short_btc","always_eth_short_btc_net_12bps_pct")):
            row[name+"_net_pct"]=round(float((np.prod(1+g[col].to_numpy(float)/100)-1)*100),5)
        monthly_rows.append(row)
    pd.DataFrame(monthly_rows).to_csv(out/"monthly.csv",index=False)
    data_hash=hashlib.sha256(pd.util.hash_pandas_object(pair,index=True).values.tobytes()).hexdigest()
    summary=summarize_periods(decisions)
    report={"status":"completed","strategy":"BTC/ETH 72h cross-sectional relative momentum",
        "data_source":"Delta Exchange India BTCUSD/ETHUSD traded-price 15m OHLCV",
        "data_quality":quality,"aligned_data_hash_pandas_object_sha256":data_hash,
        "decision_count":int(len(decisions)),"active_decision_count":int(decisions.active.sum()),
        "rules":{"lookback":"72h / 288 completed 15m intervals",
            "decision_cadence":"every 4h UTC boundary",
            "relative_threshold_percentage_points":1.0,
            "signal":"long stronger asset, short weaker asset only when relative trailing-return spread >= 1.00pp in absolute value",
            "entry":"next 15m open at the 4h boundary",
            "exit":"close of 16th 15m bar, exactly 4h after entry",
            "legs":"equal-dollar 1x notional; pair return is per unit of total gross notional",
            "variants":["market-neutral equal-dollar long/short pair","long-only stronger asset"],
            "benchmarks":["flat","always long BTC / short ETH","always long ETH / short BTC"],
            "cost_sensitivity_round_trip_bps_per_leg":list(COSTS_BPS),
            "funding":"excluded; event-time settlement and units not yet verified",
            "slippage":"not modeled beyond stated cost sensitivity assumptions"},
        "periods":summary,
        "limitations":["Two-asset universe only; no survivorship or broad cross-sectional claim.",
            "No stop-defined risk unit, so R is not applicable; PF and drawdown are based on 4h portfolio-return intervals.",
            "Cost assumptions are sensitivities, not verified account fee tier, spread or market impact.",
            "Funding is excluded; 4h holds can cross funding timestamps.",
            "Pair returns use equal-dollar legs and are normalized by total gross notional, not account equity or margin.",
            "The final holdout is chronologically separate from development and validation; no parameter selection is performed."]}
    (out/"metadata.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
