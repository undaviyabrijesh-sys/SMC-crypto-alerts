"""History replay: run the same WATCH/TRIGGER logic over past candles and score the outcomes.

    python replay.py --days 50

Limits: Yahoo only serves ~60 days of 15m data. Past news, calendar blackouts, funding and Kronos
forecasts are NOT replayed, so real alert counts will be a little lower than what this shows
(Kronos hard filter and blackouts only remove alerts). Same-candle SL/TP hits count as SL.
"""
import argparse

import pandas as pd

import config as C
import data, discord, main, news


def _outcome(m15, t, w, max_hours=48):
    bars = m15[m15.index >= t.floor("15min")]
    long = w["dir"] == "long"
    risk = abs(w["entry"] - w["sl"])
    for ts, r in bars.iterrows():
        hit_sl = r["low"] <= w["sl"] if long else r["high"] >= w["sl"]
        hit_tp = r["high"] >= w["tp"] if long else r["low"] <= w["tp"]
        if hit_sl:                       # includes the same-candle case: assume the worst
            return "SL", -1.0
        if hit_tp:
            return "TP", w["rr"]
        if ts - t > pd.Timedelta(hours=max_hours):
            pnl = (r["close"] - w["entry"]) if long else (w["entry"] - r["close"])
            return "TIMEOUT", pnl / risk
    return "OPEN", 0.0


def replay(fetcher=data.fetch, days=50, step_min=15, verbose=True):
    frames = {s: (fetcher(c["yf"], "1h", "120d"), fetcher(c["yf"], "15m", "60d")) for s, c in C.SYMBOLS.items()}
    frames = {s: f for s, f in frames.items() if f[0] is not None and f[1] is not None}
    end = min(f[1].index[-1] for f in frames.values()) + pd.Timedelta(minutes=15)
    start = end - pd.Timedelta(days=days)

    events, now_box = [], {}
    orig = (discord.send, news.headline_sentiment, news.funding_rate)
    discord.send = lambda stage, sym, w, fmt, lines=None, note=None: events.append((now_box["t"], stage, sym, dict(w)))
    news.headline_sentiment = lambda *a, **k: (0.0, 0, [])
    news.funding_rate = lambda *a, **k: None
    try:
        state = {"watches": {}, "rearm": {}, "seen": [], "log": []}
        t = start.ceil(f"{step_min}min") + pd.Timedelta(minutes=1)
        while t <= end:
            now_box["t"] = t
            for sym, cfg in C.SYMBOLS.items():
                if sym not in frames:
                    continue
                fe = lambda y, i, p, s=sym: frames[s][0] if i == "1h" else frames[s][1]
                try:
                    main.process(sym, cfg, state, t, None, True, {}, fe)
                except Exception as ex:
                    print(f"[error] {sym} {t}: {ex}")
            t += pd.Timedelta(minutes=step_min)
    finally:
        discord.send, news.headline_sentiment, news.funding_rate = orig

    rows = []
    for t, stage, sym, w in events:
        if stage == "TRIGGER":
            res, r = _outcome(frames[sym][1], t, w)
            rows.append({"sym": sym, "time": t, "dir": w["dir"], "result": res, "R": r})
    trig = pd.DataFrame(rows)
    watches = pd.Series([e[2] for e in events if e[1] == "WATCH"], dtype=str).value_counts().to_dict()
    cancels = len([e for e in events if e[1] == "CANCEL"])

    if verbose:
        out = [f"Replay {start:%Y-%m-%d} -> {end:%Y-%m-%d} ({days} days)",
               f"WATCH alerts: {sum(watches.values())} {watches} | CANCEL: {cancels}"]
        if trig.empty:
            out.append("TRIGGER alerts: 0")
        else:
            done = trig[trig.result != "OPEN"]
            for name, g in [("ALL", done)] + list(done.groupby("sym")):
                if g.empty:
                    continue
                wins = (g.result == "TP").sum()
                out.append(f"{name:>4}: {len(g)} trades ({len(g)/days:.2f}/day) | TP {wins} SL {(g.result=='SL').sum()} "
                           f"timeout {(g.result=='TIMEOUT').sum()} | win rate {wins/len(g):.0%} | avg R {g.R.mean():+.2f}")
        text = "\n".join(out)
        print("\n" + text)
        discord.post_text("```\n" + text + "\n```")
    return events, trig


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=50)
    replay(days=ap.parse_args().days)
