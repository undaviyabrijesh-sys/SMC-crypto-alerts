from . import config as C


def build_setup(zone, price, atr1, zones, tips):
    """Planned trade from a zone: buy at support / sell at resistance. TP = nearest opposing zone edge or
    unswept swing tip (liquidity). Returns None if price is not close enough, no target, or R:R too low."""
    buf = C.SL_BUFFER_ATR * atr1
    if zone["kind"] == "demand":
        d, entry, sl = "long", zone["hi"], zone["lo"] - buf
        if not (price > entry and price - entry <= C.WATCH_DIST_ATR * atr1):
            return None
        cands = [z["lo"] for z in zones if z["kind"] == "supply" and z["lo"] > entry]
        cands += [p for p in tips["highs"] if p > entry]
        tp = min(cands) if cands else None
    else:
        d, entry, sl = "short", zone["lo"], zone["hi"] + buf
        if not (price < entry and entry - price <= C.WATCH_DIST_ATR * atr1):
            return None
        cands = [z["hi"] for z in zones if z["kind"] == "demand" and z["hi"] < entry]
        cands += [p for p in tips["lows"] if p < entry]
        tp = max(cands) if cands else None
    if tp is None:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    rr = abs(tp - entry) / risk
    if rr < C.MIN_RR_WATCH:
        return None
    return {"dir": d, "entry": entry, "sl": sl, "tp": tp, "rr": rr, "dist_atr": abs(price - entry) / atr1}


def score_setup(setup, zone, ctx):
    """0-100 confluence score plus reasons. More impulse = stronger zone. No trend term by design."""
    sign = 1 if setup["dir"] == "long" else -1
    pts, why = 0.0, []

    s = zone["strength"]
    pts += 10 + 20 * min(1.0, max(0.0, (s - C.ZZ_ATR) / 3.0))
    label = "role-reversal zone" if zone["flip"] else (
        "fresh swing-tip zone" if zone["retests"] == 0 else f"swing-tip zone, held {zone['retests']} retest(s)")
    why.append(f"{label}, impulse {s:.1f} ATR")

    if zone["retests"] > 0:   # more reaction on past retests = stronger zone
        r = zone["best_reaction"]
        if r < 0.5:
            pts -= 5; why.append(f"weak past reaction ({r:.1f} ATR)")
        else:
            pts += 10 * min(1.0, max(0.0, (r - 1.0) / 2.0)); why.append(f"best retest reaction {r:.1f} ATR")

    pts += min(10, 10 * zone["gap_atr"] / 0.5)
    why.append(f"FVG {zone['gap_atr']:.1f} ATR")

    pts += 10  # sits on a real zigzag tip (always true for zones that reach here)

    pts += 10 if setup["dist_atr"] <= 0.5 else 5
    why.append(f"{setup['dist_atr']:.1f} ATR away")

    pts += 15 if setup["rr"] >= 3 else 10
    why.append(f"R:R {setup['rr']:.1f} to next liquidity/zone")

    k = ctx.get("kronos")
    if k in ("up", "down"):
        if (k == "up") == (sign == 1):
            pts += 15; why.append("Kronos agrees")
        else:
            pts -= 15; why.append("Kronos disagrees")

    f = ctx.get("funding")
    if f is not None:
        if f * sign > C.FUNDING_CROWDED:
            pts -= 5; why.append("funding crowded your way")
        elif f * sign <= 0:
            pts += 5; why.append("funding favors you")

    n = ctx.get("news", 0.0) * sign
    if abs(n) > 0.05:
        pts += 10 * n
        why.append("news supports" if n > 0 else "news conflicts")

    return max(0, min(100, round(pts))), why
