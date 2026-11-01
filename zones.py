import pandas as pd

from . import config as C


def atr(df, n: int = C.ATR_LEN):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def zigzag(df, mult: float):
    """ATR-based zigzag. Returns confirmed pivots [(idx, price, 'H'|'L')] and the still-open leg's extreme."""
    a = atr(df).values
    h, l = df["high"].values, df["low"].values
    pivots, d = [], 0
    hi_i = lo_i = 0
    hi_p, lo_p = h[0], l[0]
    for i in range(1, len(df)):
        t = mult * a[i]
        if d == 0:
            if h[i] > hi_p:
                hi_p, hi_i = h[i], i
            if l[i] < lo_p:
                lo_p, lo_i = l[i], i
            if t > 0 and hi_p - lo_p >= t:
                if hi_i > lo_i:
                    d = 1; pivots.append((lo_i, float(lo_p), "L"))
                else:
                    d = -1; pivots.append((hi_i, float(hi_p), "H"))
        elif d == 1:
            if h[i] > hi_p:
                hi_p, hi_i = h[i], i
            elif t > 0 and hi_p - l[i] >= t:
                pivots.append((hi_i, float(hi_p), "H")); d = -1; lo_p, lo_i = l[i], i
        else:
            if l[i] < lo_p:
                lo_p, lo_i = l[i], i
            elif t > 0 and h[i] - lo_p >= t:
                pivots.append((lo_i, float(lo_p), "L")); d = 1; hi_p, hi_i = h[i], i
    running = ("H", hi_i, float(hi_p)) if d == 1 else (("L", lo_i, float(lo_p)) if d == -1 else None)
    return pivots, running


def find_zones(df, sym: str):
    """Zones sit on zigzag tips. Demand = the lowest candle at the origin of an impulse that leaves an FVG;
    supply is the mirror. One zone per tip, never per minor swing. Zone box = that tip candle's high/low.

    A zone stays valid until a body close breaks it. Retests do NOT use it up: we count them and measure how far
    price reacted each time (more reaction = stronger zone). A break with follow-through flips the role
    (broken support becomes resistance and the reverse); a break without follow-through kills the zone.
    Returns (zones, tips); tips = unswept swing highs/lows, used as liquidity targets."""
    n = len(df)
    a = atr(df).values
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    pivots, running = zigzag(df, C.ZZ_ATR)
    seq = [(p[0], p[1], p[2]) for p in pivots] + ([(running[1], running[2], running[0])] if running else [])
    min_idx = n - C.ZONE_MAX_AGE_BARS
    zones = []
    for k, (t, price, typ) in enumerate(pivots):
        if t < min_idx or not a[t] > 0:
            continue
        end_i, end_p, _ = seq[k + 1]
        strength = abs(end_p - price) / a[t]
        lo, hi = float(l[t]), float(h[t])
        if hi - lo > C.ZONE_MAX_WIDTH_ATR * a[t]:
            continue
        demand = typ == "L"
        gap = 0.0
        for kk in range(t, min(t + C.FVG_MAX_OFFSET, n - 3) + 1):
            gap = max(gap, (l[kk + 2] - h[kk]) if demand else (l[kk] - h[kk + 2]))
        if gap < C.FVG_MIN_ATR * a[t]:
            continue
        dep = next((m for m in range(t + 1, n) if (c[m] > hi if demand else c[m] < lo)), None)
        if dep is None:
            continue

        # Walk forward: record retests, handle breaks and role flips.
        origin = kind = "demand" if demand else "supply"
        retest_idx, dead, pending = [], False, False
        for m in range(dep + 1, n):
            if kind == "demand":
                if c[m] < lo:
                    if m + C.IMPULSE_BARS >= n:
                        pending = True; break          # not enough candles yet to judge follow-through
                    disp = (lo - l[m:m + C.IMPULSE_BARS + 1].min()) / a[m]
                    if disp >= C.FLIP_MIN_ATR:
                        kind, strength, retest_idx = "supply", disp, []
                    else:
                        dead = True; break
                elif l[m] <= hi:
                    retest_idx.append(m)
            else:
                if c[m] > hi:
                    if m + C.IMPULSE_BARS >= n:
                        pending = True; break
                    disp = (h[m:m + C.IMPULSE_BARS + 1].max() - hi) / a[m]
                    if disp >= C.FLIP_MIN_ATR:
                        kind, strength, retest_idx = "demand", disp, []
                    else:
                        dead = True; break
                elif h[m] >= lo:
                    retest_idx.append(m)
        if dead or pending:
            continue

        groups = []                                    # consecutive touching candles = one retest
        for m in retest_idx:
            if groups and m - groups[-1][-1] <= 1:
                groups[-1].append(m)
            else:
                groups.append([m])
        done = [g for g in groups if g[-1] < n - 1]    # a retest still in progress is not counted yet
        reacts = []
        for g in done:
            e = g[-1]
            win = slice(e + 1, min(e + 1 + C.REACT_BARS, n))
            reacts.append(((h[win].max() - hi) if kind == "demand" else (lo - l[win].min())) / a[e])
        flipped = kind != origin
        stamp = df.index[t].strftime("%Y%m%d%H%M")
        zones.append({"id": f"{sym}-{kind}-{stamp}" + ("-flip" if flipped else ""), "kind": kind,
                      "lo": lo, "hi": hi, "strength": float(strength), "gap_atr": float(gap / a[t]),
                      "formed": df.index[t].isoformat(), "flip": flipped,
                      "retests": len(done), "best_reaction": float(max(reacts)) if reacts else 0.0})

    highs, lows = [], []
    for i, p, typ in seq:
        rest = slice(i + 1, n)
        if typ == "H" and (i + 1 >= n or h[rest].max() <= p):
            highs.append(p)
        if typ == "L" and (i + 1 >= n or l[rest].min() >= p):
            lows.append(p)
    return zones, {"highs": highs, "lows": lows}
