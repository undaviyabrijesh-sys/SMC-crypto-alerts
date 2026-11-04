import json
import os
import uuid

import pandas as pd

import config as C
import data, discord, news, state as st
from score import build_setup, score_setup
from zones import atr, find_zones

_ZC = {}


def load_kronos():
    path = os.environ.get("KRONOS_BIAS_FILE", "kronos_bias.json")
    try:
        raw = json.load(open(path))
        return {str(k).upper(): str(v).lower() for k, v in raw.items()
                if str(v).lower() in ("up", "down", "flat")}
    except (OSError, ValueError, TypeError):
        return {}


def _log(state, now, stage, sym, w):
    state.setdefault("log", []).append({
        "t": now.isoformat(), "stage": stage, "sym": sym, "id": w["id"],
        "dir": w["dir"], "entry": w["entry"], "sl": w["sl"], "tp": w["tp"],
        "rr": round(w["rr"], 2), "score": w.get("score"),
    })


def _close(state, w, now):
    state["watches"].pop(w["id"], None)
    state.setdefault("rearm", {})[w["id"]] = {
        "t": now.isoformat(), "dir": w["dir"], "lo": w["lo"], "hi": w["hi"],
    }


def check_rearm(state, sym, m15, atr1, now):
    for zid, r in list(state.setdefault("rearm", {}).items()):
        if not zid.startswith(f"{sym}-"):
            continue
        t = pd.Timestamp(r["t"])
        if now - t > pd.Timedelta(days=15):
            del state["rearm"][zid]
            continue
        bars = m15[m15.index >= t.floor("15min")]
        if bars.empty:
            continue
        if r["dir"] == "long":
            extreme_i = bars["high"].idxmax()
            moved_away = bars["high"].max() - r["hi"] >= C.REARM_ATR * atr1
            returned = bars.index[-1] > extreme_i and bars["low"].iloc[-1] <= r["hi"] + 0.25 * atr1
        else:
            extreme_i = bars["low"].idxmin()
            moved_away = r["lo"] - bars["low"].min() >= C.REARM_ATR * atr1
            returned = bars.index[-1] > extreme_i and bars["high"].iloc[-1] >= r["lo"] - 0.25 * atr1
        if moved_away and returned:
            del state["rearm"][zid]


def _trend(h1):
    close = h1["close"]
    fast = close.ewm(span=C.TREND_EMA_FAST, adjust=False).mean()
    slow = close.ewm(span=C.TREND_EMA_SLOW, adjust=False).mean()
    slope = slow.iloc[-1] - slow.iloc[-1-C.TREND_SLOPE_BARS]
    if close.iloc[-1] > slow.iloc[-1] and fast.iloc[-1] > slow.iloc[-1] and slope > 0:
        return "up"
    if close.iloc[-1] < slow.iloc[-1] and fast.iloc[-1] < slow.iloc[-1] and slope < 0:
        return "down"
    return "flat"


def _validate_ohlc(df, label):
    if df is None or df.empty:
        raise ValueError(f"{label}: empty candle data")
    required = ["open", "high", "low", "close"]
    if not set(required).issubset(df.columns):
        raise ValueError(f"{label}: missing OHLC columns")
    if df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError(f"{label}: duplicate or unsorted timestamps")
    if df[required].isna().any().any():
        raise ValueError(f"{label}: null OHLC")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError(f"{label}: invalid high")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"{label}: invalid low")


def manage_watches(state, sym, m15, atr1, now, blackout, fmt):
    for w in [x for x in state["watches"].values() if x["sym"] == sym]:
        created = pd.Timestamp(w["created"])
        bars = m15[m15.index >= created]
        if now-created > pd.Timedelta(hours=C.WATCH_EXPIRY_HOURS):
            discord.send("CANCEL", sym, w, fmt, note="Expired without a confirmed reaction.")
            _log(state, now, "EXPIRE", sym, w)
            _close(state, w, now)
            continue
        if bars.empty:
            continue
        long = w["dir"] == "long"
        broken = (bars["close"] < w["lo"]).any() if long else (bars["close"] > w["hi"]).any()
        if broken:
            discord.send("CANCEL", sym, w, fmt, note="Zone invalidated by 15m body close.")
            _log(state, now, "CANCEL", sym, w)
            _close(state, w, now)
            continue
        touched = (bars["low"] <= w["hi"]) if long else (bars["high"] >= w["lo"])
        if not touched.any() or blackout:
            continue
        after = bars.iloc[int(touched.values.argmax()):]
        if long:
            reactions = after[(after["close"] > w["hi"]) & (after["close"] > after["open"])]
        else:
            reactions = after[(after["close"] < w["lo"]) & (after["close"] < after["open"])]
        if reactions.empty:
            continue

        trigger_time = reactions.index[-1]
        entry = float(reactions.iloc[-1]["close"])
        rejection = after.loc[:trigger_time]
        buffer = C.SL_BUFFER_ATR * atr1
        sl = float(rejection["low"].min()-buffer) if long else float(rejection["high"].max()+buffer)
        risk = abs(entry-sl)
        risk_atr = risk/atr1 if atr1 else float("inf")
        good_side = entry < w["tp"] if long else entry > w["tp"]
        rr = abs(w["tp"]-entry)/risk if risk > 0 and good_side else 0.0
        drift = abs(entry-float(w["entry"]))/atr1 if atr1 else float("inf")
        reason = None
        if not good_side:
            reason = "Target no longer lies in trade direction."
        elif risk_atr < C.MIN_STOP_ATR_TRIGGER:
            reason = f"Stop too tight ({risk_atr:.2f} ATR)."
        elif risk_atr > C.MAX_STOP_ATR_TRIGGER:
            reason = f"Stop too wide ({risk_atr:.2f} ATR)."
        elif drift > C.MAX_ENTRY_DRIFT_ATR:
            reason = f"Entry drift {drift:.2f} ATR; no chasing."
        elif rr < C.MIN_RR_TRIGGER:
            reason = f"Confirmed R:R only {rr:.1f}; skip."
        if reason:
            discord.send("CANCEL", sym, w, fmt, note=reason)
            _log(state, now, "CANCEL", sym, w)
            _close(state, w, now)
            continue

        trade = dict(w, entry=entry, sl=sl, rr=rr, trigger_time=trigger_time.isoformat(),
                     risk_atr=risk_atr, entry_drift_atr=drift)
        signal_id = uuid.uuid4().hex[:12].upper()
        trade["signal_id"] = signal_id
        discord.send("TRIGGER", sym, trade, fmt, lines=[
            "15m rejection confirmed at 1h zone",
            f"1h trend aligned: {w.get('trend','flat').upper()}",
            f"Stop={risk_atr:.2f} ATR | entry drift={drift:.2f} ATR",
        ])
        state.setdefault("positions", {})[signal_id] = {
            "signal_id": signal_id, "sym": sym, "dir": trade["dir"],
            "entry": entry, "sl": sl, "tp": float(trade["tp"]), "rr": rr,
            "triggered_at": trigger_time.isoformat(), "zone_id": trade["id"],
            "zone_lo": float(trade["lo"]), "zone_hi": float(trade["hi"]),
            "score": trade.get("score"), "trend": trade.get("trend"), "status": "OPEN",
        }
        _log(state, now, "TRIGGER", sym, trade)
        _close(state, w, now)


def manage_positions(state, sym, m15, now, fmt):
    positions = state.setdefault("positions", {})
    for sid, trade in list(positions.items()):
        if trade["sym"] != sym:
            continue
        t0 = pd.Timestamp(trade["triggered_at"])
        future = m15[m15.index > t0]
        if future.empty:
            continue
        long = trade["dir"] == "long"
        outcome = exit_price = exit_ts = None
        for ts, bar in future.iterrows():
            op, hi, lo = (float(bar[k]) for k in ("open","high","low"))
            sl, tp = float(trade["sl"]), float(trade["tp"])
            if long:
                if op <= sl: exit_price, outcome = op, "SL"
                elif op >= tp: exit_price, outcome = op, "TP"
                elif lo <= sl: exit_price, outcome = sl, "SL"
                elif hi >= tp: exit_price, outcome = tp, "TP"
            else:
                if op >= sl: exit_price, outcome = op, "SL"
                elif op <= tp: exit_price, outcome = op, "TP"
                elif hi >= sl: exit_price, outcome = sl, "SL"
                elif lo <= tp: exit_price, outcome = sl, "SL"
                elif lo <= tp: exit_price, outcome = tp, "TP"
            if outcome:
                exit_ts = ts
                break
        if not outcome and now-t0 > pd.Timedelta(hours=C.TRADE_MAX_HOURS):
            exit_ts, exit_price, outcome = future.index[-1], float(future.iloc[-1]["close"]), "TIME"
        if not outcome:
            continue
        entry = float(trade["entry"])
        risk = abs(entry-float(trade["sl"]))
        direction = 1 if long else -1
        pnl_r = ((float(exit_price)-entry)/risk*direction) if risk else 0.0
        result = {**trade, "status": outcome, "exit": float(exit_price),
                  "exit_time": str(exit_ts), "gross_R": round(pnl_r,4),
                  "gross_pnl_pct": round((float(exit_price)-entry)/entry*direction*100,4)}
        state.setdefault("trade_history", []).append(result)
        state["trade_history"] = state["trade_history"][-1000:]
        del positions[sid]
        discord.send_outcome(result, fmt)
        print(f"[closed] {sym} {sid}: {outcome} {pnl_r:+.2f}R")


def process(sym, cfg, state, now, blackout, cal_ok, kronos, fetcher):
    h1 = data.closed_only(fetcher(cfg["yf"], "1h", "120d"), 60, now)
    m15 = data.closed_only(fetcher(cfg["yf"], "15m", "5d"), 15, now)
    _validate_ohlc(h1, f"{sym} 1h")
    _validate_ohlc(m15, f"{sym} 15m")
    if data.is_stale(h1,60,now) or data.is_stale(m15,15,now):
        print(f"[skip] {sym}: stale feed")
        return
    min_h1 = max(C.ATR_LEN+5, C.TREND_EMA_SLOW+C.TREND_SLOPE_BARS+5, 100)
    if len(h1) < min_h1 or len(m15) < 10:
        print(f"[skip] {sym}: insufficient history")
        return
    a = atr(h1).iloc[-1]
    if pd.isna(a) or a <= 0:
        print(f"[skip] {sym}: invalid ATR")
        return
    atr1 = float(a)
    fmt = lambda x: f"{x:.{cfg['dp']}f}"
    price = float(m15["close"].iloc[-1])
    trend = _trend(h1)

    manage_positions(state, sym, m15, now, fmt)
    manage_watches(state, sym, m15, atr1, now, blackout, fmt)
    check_rearm(state, sym, m15, atr1, now)
    if blackout:
        return
    active = [w for w in state["watches"].values() if w["sym"] == sym]
    if any(p["sym"] == sym for p in state.setdefault("positions", {}).values()):
        return
    if len(active) >= C.MAX_ACTIVE_PER_SYMBOL:
        return

    key = (sym, h1.index[-1], float(h1["close"].iloc[-1]), float(h1["low"].iloc[-1]))
    if _ZC.get(sym, (None,))[0] != key:
        _ZC[sym] = (key, find_zones(h1, sym))
    zones, tips = _ZC[sym][1]
    known = set(state["watches"]) | set(state["rearm"])
    ctx = None
    for zone in zones:
        if zone["id"] in known or zone["retests"] > C.MAX_ZONE_RETESTS:
            continue
        setup = build_setup(zone, price, atr1, zones, tips)
        if not setup:
            continue
        direction = "up" if setup["dir"] == "long" else "down"
        bias = kronos.get(sym)
        if C.KRONOS_HARD_FILTER and bias is not None and bias != direction:
            continue
        if C.TREND_FILTER_ENABLED and trend != direction:
            continue
        if ctx is None:
            sentiment, _, _ = news.headline_sentiment(cfg["kind"], cfg["news_q"], now)
            ctx = {"kronos": bias, "news": sentiment, "funding": news.funding_rate(cfg["okx"])}
        score, why = score_setup(setup, zone, ctx)
        if score < C.WATCH_MIN_SCORE:
            continue
        why.append(f"1h EMA structure aligned ({trend})")
        watch = {
            "id": zone["id"], "sym": sym, "lo": zone["lo"], "hi": zone["hi"],
            "created": now.isoformat(), "score": score, "flip": zone["flip"],
            "trend": trend, **setup,
        }
        notes = []
        if not cal_ok:
            notes.append("Economic calendar unavailable; check manually.")
        if C.KRONOS_HARD_FILTER and bias is None:
            notes.append("Kronos bias unavailable; no Kronos filter applied.")
        discord.send("WATCH", sym, watch, fmt, lines=why, note="\n".join(notes) or None)
        state["watches"][watch["id"]] = watch
        active.append(watch)
        _log(state, now, "WATCH", sym, watch)


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
            process(sym,cfg,state,now,blackout,cal_ok,kronos,fetcher)
        except Exception as ex:
            print(f"[error] {sym}: {ex}")
    st.save(state)


if __name__ == "__main__":
    run()
