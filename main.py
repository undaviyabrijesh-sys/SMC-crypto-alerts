import json
import os

import pandas as pd

from . import config as C
from . import data, discord, news, state as st
from .score import build_setup, score_setup
from .zones import atr, find_zones


def load_kronos():
    """Optional hook: your Kronos job writes {"BTC": "up", "ETH": "down", "XAU": "flat"} to this file."""
    path = os.environ.get("KRONOS_BIAS_FILE", "kronos_bias.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _log(state, now, stage, sym, w):
    state["log"].append({"t": now.isoformat(), "stage": stage, "sym": sym, "id": w["id"], "dir": w["dir"],
                         "entry": w["entry"], "sl": w["sl"], "tp": w["tp"], "rr": round(w["rr"], 2),
                         "score": w.get("score")})


def _close(state, w, now):
    """Close a watch. The same zone may alert again, but only after price has moved away and come back."""
    state["watches"].pop(w["id"], None)
    state.setdefault("rearm", {})[w["id"]] = {"t": now.isoformat(), "dir": w["dir"], "lo": w["lo"], "hi": w["hi"]}


def check_rearm(state, sym, m15, atr1, now):
    for zid, r in list(state.setdefault("rearm", {}).items()):
        t = pd.Timestamp(r["t"])
        if now - t > pd.Timedelta(days=15):
            del state["rearm"][zid]; continue
        if not zid.startswith(f"{sym}-"):
            continue
        bars = m15[m15.index >= t.floor("15min")]
        if bars.empty:
            continue
        away = (bars["high"].max() - r["hi"]) if r["dir"] == "long" else (r["lo"] - bars["low"].min())
        if away >= C.REARM_ATR * atr1:
            del state["rearm"][zid]


def manage_watches(state, sym, m15, atr1, now, blackout, fmt):
    for w in [x for x in state["watches"].values() if x["sym"] == sym]:
        created = pd.Timestamp(w["created"])
        if now - created > pd.Timedelta(hours=C.WATCH_EXPIRY_HOURS):
            discord.send("CANCEL", sym, w, fmt, note="Expired: no reaction at the zone.")
            _log(state, now, "EXPIRE", sym, w); _close(state, w, now); continue
        bars = m15[m15.index >= created]
        if bars.empty:
            continue
        long = w["dir"] == "long"
        broke = (bars["close"] < w["lo"]).any() if long else (bars["close"] > w["hi"]).any()
        if broke:
            discord.send("CANCEL", sym, w, fmt, note="Zone broken. Setup invalid.")
            _log(state, now, "CANCEL", sym, w); _close(state, w, now); continue
        entered = (bars["low"] <= w["hi"]) if long else (bars["high"] >= w["lo"])
        if not entered.any():
            continue
        after = bars.iloc[int(entered.values.argmax()):]
        recent = after.iloc[-2:]
        if long:
            react = recent[(recent["close"] > w["hi"]) & (recent["close"] > recent["open"])]
        else:
            react = recent[(recent["close"] < w["lo"]) & (recent["close"] < recent["open"])]
        if react.empty or blackout:
            continue
        entry = float(react["close"].iloc[-1])
        buf = C.SL_BUFFER_ATR * atr1
        sl = float(after["low"].min() - buf) if long else float(after["high"].max() + buf)
        risk = abs(entry - sl)
        good_side = entry < w["tp"] if long else entry > w["tp"]
        rr = abs(w["tp"] - entry) / risk if risk > 0 and good_side else 0
        if rr < C.MIN_RR_TRIGGER:
            discord.send("CANCEL", sym, w, fmt, note=f"Reaction came but R:R is only {rr:.1f}. Skip.")
            _log(state, now, "CANCEL", sym, w); _close(state, w, now); continue
        t = dict(w, entry=entry, sl=sl, rr=rr)
        discord.send("TRIGGER", sym, t, fmt, lines=["Rejection at zone confirmed on 15m close"])
        _log(state, now, "TRIGGER", sym, t); _close(state, w, now)


def process(sym, cfg, state, now, blackout, cal_ok, kronos, fetcher):
    h1 = data.closed_only(fetcher(cfg["yf"], "1h", "120d"), 60, now)
    m15 = data.closed_only(fetcher(cfg["yf"], "15m", "5d"), 15, now)
    if data.is_stale(h1, 60, now) or data.is_stale(m15, 15, now):
        print(f"[skip] {sym}: no fresh data (market closed?)")
        return
    fmt = lambda x: f"{x:.{cfg['dp']}f}"
    atr1 = float(atr(h1).iloc[-1])
    price = float(m15["close"].iloc[-1])

    manage_watches(state, sym, m15, atr1, now, blackout, fmt)
    check_rearm(state, sym, m15, atr1, now)

    if blackout:
        return
    active = [x for x in state["watches"].values() if x["sym"] == sym]
    if len(active) >= C.MAX_ACTIVE_PER_SYMBOL:
        return
    zones, tips = find_zones(h1, sym)
    known = set(state["watches"]) | set(state["rearm"])
    ctx = None
    for z in zones:
        if z["id"] in known or len(active) >= C.MAX_ACTIVE_PER_SYMBOL:
            continue
        setup = build_setup(z, price, atr1, zones, tips)
        if not setup:
            continue
        sign = 1 if setup["dir"] == "long" else -1
        k = kronos.get(sym)
        if C.KRONOS_HARD_FILTER and k is not None and k != ("up" if sign == 1 else "down"):
            print(f"[skip] {sym} {z['id']}: Kronos says {k}")
            continue
        if ctx is None:  # network context only once a candidate has passed the hard gates
            s_, n_, samples = news.headline_sentiment(cfg["kind"], cfg["news_q"], now)
            ctx = {"kronos": k, "news": s_, "funding": news.funding_rate(cfg["okx"])}
        score, why = score_setup(setup, z, ctx)
        if score < C.WATCH_MIN_SCORE:
            print(f"[skip] {sym} {z['id']} score {score} < {C.WATCH_MIN_SCORE}: {', '.join(why)}")
            continue
        w = {"id": z["id"], "sym": sym, "lo": z["lo"], "hi": z["hi"], "created": now.isoformat(),
             "score": score, "flip": z["flip"], **setup}
        notes = []
        if not cal_ok:
            notes.append("⚠ Economic calendar unavailable, check news manually.")
        if C.KRONOS_HARD_FILTER and k is None:
            notes.append("ℹ Kronos bias not connected, so this alert is not Kronos-filtered.")
        discord.send("WATCH", sym, w, fmt, lines=why, note="\n".join(notes) or None)
        state["watches"][w["id"]] = w
        active.append(w)
        _log(state, now, "WATCH", sym, w)


def run(now=None, fetcher=data.fetch):
    now = now or pd.Timestamp.now(tz="UTC")
    state = st.load()
    events, cal_ok = news.get_events()
    blackout = news.in_blackout(events, now)
    if blackout:
        print(f"[info] blackout: {blackout['title']} at {blackout['time']}")
    kronos = load_kronos()
    for sym, cfg in C.SYMBOLS.items():
        try:
            process(sym, cfg, state, now, blackout, cal_ok, kronos, fetcher)
        except Exception as ex:
            print(f"[error] {sym}: {ex}")
    st.save(state)


if __name__ == "__main__":
    run()
