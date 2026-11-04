import config as C


def build_setup(zone, price, atr1, zones, tips):
    if atr1 <= 0:
        return None
    buffer = C.SL_BUFFER_ATR * atr1
    if zone["kind"] == "demand":
        direction, entry, sl = "long", zone["hi"], zone["lo"]-buffer
        if not (price > entry and price-entry <= C.WATCH_DIST_ATR*atr1):
            return None
        targets = [z["lo"] for z in zones if z["kind"]=="supply" and z["lo"]>entry]
        targets += [p for p in tips["highs"] if p>entry]
        tp = min(targets) if targets else None
    else:
        direction, entry, sl = "short", zone["lo"], zone["hi"]+buffer
        if not (price < entry and entry-price <= C.WATCH_DIST_ATR*atr1):
            return None
        targets = [z["hi"] for z in zones if z["kind"]=="demand" and z["hi"]<entry]
        targets += [p for p in tips["lows"] if p<entry]
        tp = max(targets) if targets else None
    risk = abs(entry-sl)
    if tp is None or risk <= 0:
        return None
    rr = abs(tp-entry)/risk
    if rr < C.MIN_RR_WATCH:
        return None
    return {"dir":direction,"entry":entry,"sl":sl,"tp":tp,"rr":rr,
            "dist_atr":abs(price-entry)/atr1}


def score_setup(setup, zone, ctx):
    """Heuristic ranking only; it is not a probability of winning."""
    sign = 1 if setup["dir"]=="long" else -1
    points, why = 0.0, []
    strength = zone["strength"]
    points += 10+20*min(1.0,max(0.0,(strength-C.ZZ_ATR)/3.0))
    why.append(("role-reversal" if zone["flip"] else "swing-tip") +
               f" zone; impulse {strength:.1f} ATR")
    if zone["retests"]:
        reaction = zone["best_reaction"]
        if reaction < 0.5:
            points -= 5
            why.append(f"weak previous reaction {reaction:.1f} ATR")
        else:
            points += 10*min(1.0,max(0.0,(reaction-1.0)/2.0))
            why.append(f"previous reaction {reaction:.1f} ATR")
    points += min(10,10*zone["gap_atr"]/0.5)
    why.append(f"FVG {zone['gap_atr']:.1f} ATR")
    points += 10
    points += 10 if setup["dist_atr"]<=0.5 else 5
    why.append(f"{setup['dist_atr']:.1f} ATR from entry")
    points += 15 if setup["rr"]>=3 else 10
    why.append(f"planned R:R {setup['rr']:.1f}")
    bias = ctx.get("kronos")
    if bias in ("up","down"):
        if (bias=="up")==(sign==1):
            points += 10
            why.append("Kronos aligned")
        else:
            points -= 10
            why.append("Kronos against")
    funding = ctx.get("funding")
    if funding is not None:
        if funding*sign > C.FUNDING_CROWDED:
            points -= 5
            why.append("funding crowded")
        elif funding*sign <= 0:
            points += 5
            why.append("funding supportive")
    news_score = ctx.get("news",0.0)*sign
    if abs(news_score)>0.05:
        points += 5*news_score
        why.append("headline tone supportive" if news_score>0 else "headline tone conflicting")
    return max(0,min(100,round(points))), why
