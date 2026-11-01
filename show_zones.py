"""List every active zone per symbol so you can compare with your chart.

    python show_zones.py

Prints the report and, if a Discord webhook secret is set, posts it there too
(DISCORD_ZONES_WEBHOOK, else DISCORD_WATCH_WEBHOOK, else DISCORD_WEBHOOK).
"""
import pandas as pd

import config as C
import data
import discord
from zones import atr, find_zones

MAX_ZONES = 8


def report(fetcher=data.fetch, now=None):
    now = now or pd.Timestamp.now(tz="UTC")
    blocks = []
    for sym, cfg in C.SYMBOLS.items():
        h1 = data.closed_only(fetcher(cfg["yf"], "1h", "120d"), 60, now)
        m15 = data.closed_only(fetcher(cfg["yf"], "15m", "5d"), 15, now)
        if data.is_stale(h1, 60, now) or data.is_stale(m15, 15, now):
            blocks.append(f"{sym}: no fresh data (market closed?)")
            continue
        a = float(atr(h1).iloc[-1])
        price = float(m15["close"].iloc[-1])
        zones, tips = find_zones(h1, sym)
        f = lambda x: f"{x:,.{cfg['dp']}f}"

        def dist(z):
            return (price - z["hi"]) if price > z["hi"] else ((z["lo"] - price) if price < z["lo"] else 0.0)

        lines = [f"{sym}  price {f(price)} | 1h ATR {f(a)}"]
        if not zones:
            lines.append("  no active zones")
        for z in sorted(zones, key=dist)[:MAX_ZONES]:
            d = dist(z) / a
            where = "price inside zone" if d == 0 else (f"price {d:.1f} ATR above zone" if price > z["hi"] else f"price {d:.1f} ATR below zone")
            age = (now - pd.Timestamp(z["formed"])).total_seconds() / 86400
            lines.append(f"  {z['kind'].upper():6}{' FLIP' if z['flip'] else ''} {f(z['lo'])} - {f(z['hi'])}")
            lines.append(f"     {where} | impulse {z['strength']:.1f} ATR | "
                         f"tested {z['retests']}x (best {z['best_reaction']:.1f}) | {age:.1f}d old")
        up = sorted(set(p for p in tips["highs"] if p > price))[:2]
        dn = sorted(set(p for p in tips["lows"] if p < price), reverse=True)[:2]
        lines.append("  liquidity above: " + (", ".join(f(p) for p in up) or "none"))
        lines.append("  liquidity below: " + (", ".join(f(p) for p in dn) or "none"))
        blocks.append("\n".join(lines))
    return blocks


if __name__ == "__main__":
    for block in report():
        print(block + "\n")
        discord.post_text("```\n" + block + "\n```")
