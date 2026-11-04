"""Chronological closed-candle replay; approximate, not tick-level execution simulation."""
import argparse
import pandas as pd
import config as C
import data, discord, main, news


def _outcome(m15, trigger_time, trade, max_hours=48, cost_bps=5.0):
    future = m15[m15.index > trigger_time]
    long = trade["dir"]=="long"
    risk = abs(float(trade["entry"])-float(trade["sl"]))
    if risk<=0:
        return "INVALID",0.0
    cost = float(trade["entry"])*cost_bps/10000.0
    for ts,bar in future.iterrows():
        op,hi,lo = float(bar.open),float(bar.high),float(bar.low)
        sl,tp = float(trade["sl"]),float(trade["tp"])
        if long:
            if op<=sl: exit_price,result=op,"SL"
            elif op>=tp: exit_price,result=op,"TP"
            elif lo<=sl: exit_price,result=sl,"SL"
            elif hi>=tp: exit_price,result=tp,"TP"
            else: continue
            pnl=exit_price-float(trade["entry"])-cost
        else:
            if op>=sl: exit_price,result=op,"SL"
            elif op<=tp: exit_price,result=op,"TP"
            elif hi>=sl: exit_price,result=sl,"SL"
            elif lo<=tp: exit_price,result=tp,"TP"
            else: continue
            pnl=float(trade["entry"])-exit_price-cost
        return result,pnl/risk
    if not future.empty and future.index[-1]-trigger_time>=pd.Timedelta(hours=max_hours):
        exit_price=float(future.iloc[-1].close)
        pnl=(exit_price-float(trade["entry"]))*(1 if long else -1)-cost
        return "TIME",pnl/risk
    return "OPEN",0.0


def replay(fetcher=data.fetch,days=50,step_min=15,verbose=True,cost_bps=5.0):
    frames={}
    for sym,cfg in C.SYMBOLS.items():
        h1=fetcher(cfg["yf"],"1h","120d")
        m15=fetcher(cfg["yf"],"15m","60d")
        if h1 is None or m15 is None or h1.empty or m15.empty:
            continue
        frames[sym]=(h1,m15)
    if not frames:
        raise RuntimeError("No usable OHLC data returned")
    end=min(v[1].index[-1] for v in frames.values())+pd.Timedelta(minutes=15)
    start=end-pd.Timedelta(days=days)
    events,box=[],{}
    original=(discord.send,discord.send_outcome,news.headline_sentiment,news.funding_rate)
    discord.send=lambda stage,sym,w,fmt,lines=None,note=None: events.append((box["now"],stage,sym,dict(w)))
    discord.send_outcome=lambda *a,**k: None
    news.headline_sentiment=lambda *a,**k:(0.0,0,[])
    news.funding_rate=lambda *a,**k:None
    try:
        state={"watches":{},"positions":{},"trade_history":[],"rearm":{},"seen":[],"log":[]}
        main._ZC.clear()
        t=start.ceil(f"{step_min}min")
        while t<=end:
            box["now"]=t
            for sym,cfg in C.SYMBOLS.items():
                if sym not in frames:
                    continue
                h1,m15=frames[sym]
                hnow=h1[h1.index<=t-pd.Timedelta(hours=1)]
                mnow=m15[m15.index<=t-pd.Timedelta(minutes=15)]
                if len(hnow)<100 or len(mnow)<10:
                    continue
                fetch_slice=lambda y,i,p,h=hnow,m=mnow: h if i=="1h" else m
                try:
                    main.process(sym,cfg,state,t,None,True,{},fetch_slice)
                except Exception as ex:
                    if verbose: print(f"[replay error] {sym} {t}: {ex}")
            t+=pd.Timedelta(minutes=step_min)
    finally:
        discord.send,discord.send_outcome,news.headline_sentiment,news.funding_rate=original
        main._ZC.clear()
    rows=[]
    for ts,stage,sym,trade in events:
        if stage!="TRIGGER":
            continue
        trigger=pd.Timestamp(trade.get("trigger_time",ts))
        result,r=_outcome(frames[sym][1],trigger,trade,C.TRADE_MAX_HOURS,cost_bps)
        rows.append({"sym":sym,"time":trigger,"dir":trade["dir"],"score":trade.get("score"),
                     "trend":trade.get("trend"),"result":result,"R":r})
    trades=pd.DataFrame(rows)
    done=trades[trades.result!="OPEN"] if not trades.empty else trades
    if verbose:
        print(f"Replay: {start} -> {end} UTC | assumed cost {cost_bps:.1f} bps")
        print(f"WATCH={sum(e[1]=='WATCH' for e in events)} | TRIGGER={len(trades)}")
        if done.empty:
            print("No completed trades")
        else:
            for label,g in [("ALL",done)]+list(done.groupby("sym")):
                wins=int((g.result=="TP").sum())
                print(f"{label}: n={len(g)}, TP={wins}, SL={int((g.result=='SL').sum())}, "
                      f"TIME={int((g.result=='TIME').sum())}, win rate={wins/len(g):.1%}, "
                      f"expectancy={g.R.mean():+.2f}R")
        print(f"Still open: {int((trades.result=='OPEN').sum()) if not trades.empty else 0}")
        discord.post_text("Replay complete; inspect workflow logs for detailed results.")
    return events,trades


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--days",type=int,default=50)
    parser.add_argument("--cost-bps",type=float,default=5.0)
    args=parser.parse_args()
    replay(days=args.days,cost_bps=args.cost_bps)
